"""Notas do IMDb obtidas pela OMDb API (https://www.omdbapi.com/).

O IMDb não oferece API pública gratuita; a OMDb expõe a nota e os votos do IMDb
por `imdb_id` ou por título e ano. O provedor enriquece conteúdos de
filmes e séries e alimenta o seed `services.catalog.seed_omdb`; não participa da
busca nem da importação pela interface.
"""

import re
from datetime import datetime

import httpx

from reviewhub_core.external import ExternalContent
from services.catalog.providers.base import ProviderError, RateGate, TTLCache, request

IMDB_ID = re.compile(r"^tt\d{7,10}$")
KINDS = {"movies": "movie", "series": "series"}


def _list(value):
    if not isinstance(value, str) or value == "N/A":
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _number(value, cast):
    if not isinstance(value, str) or value in ("", "N/A"):
        return None
    try:
        return cast(value.replace(",", ""))
    except ValueError:
        return None


class OMDbProvider:
    def __init__(self, api_key: str, client=None):
        self.api_key = api_key
        self.client = client or httpx.Client()
        self.gate = RateGate(0.1)
        self.cache = TTLCache(ttl=3600)

    def _get(self, params):
        data = self.gate.call(
            lambda: request(
                self.client,
                "GET",
                "https://www.omdbapi.com/",
                params={"apikey": self.api_key, **params},
            )
        )
        # A OMDb responde 200 com Response=False para conteúdo inexistente.
        if data.get("Response") == "False":
            error = str(data.get("Error", ""))
            if "not found" in error.casefold():
                raise ProviderError("Conteúdo não encontrado no IMDb", 404)
            if "limit" in error.casefold():
                raise ProviderError(
                    "Limite do provedor atingido; tente novamente mais tarde", 429
                )
            raise ProviderError("Provedor não autorizado ou indisponível", 503)
        return data

    def ratings(
        self,
        domain: str,
        imdb_id: str | None = None,
        title: str | None = None,
        year: int | None = None,
    ) -> dict:
        if domain not in KINDS:
            raise ProviderError("Domínio incompatível com o provedor", 404)
        if imdb_id:
            if not IMDB_ID.match(imdb_id):
                raise ProviderError("Identificador IMDb inválido", 422)
            key, params = ("id", imdb_id), {"i": imdb_id}
        elif title:
            params = {"t": title, "type": KINDS[domain]}
            if year:
                params["y"] = str(year)
            key = ("title", domain, title.casefold(), year)
        else:
            raise ProviderError("Informe imdb_id ou título", 422)
        data = self.cache.get_or_load(key, lambda: self._get(params))
        return self.normalize(data)

    def get_details(self, imdb_id: str, domain: str) -> ExternalContent:
        if domain not in KINDS:
            raise ProviderError("Domínio incompatível com o provedor", 404)
        if not IMDB_ID.match(imdb_id):
            raise ProviderError("Identificador IMDb inválido", 422)
        data = self.cache.get_or_load(
            ("details", imdb_id),
            lambda: self._get({"i": imdb_id, "plot": "full"}),
        )
        if data.get("imdbID") != imdb_id or data.get("Type") != KINDS[domain]:
            raise ProviderError("Resposta externa incompatível", 502)
        return self.normalize_content(data, domain)

    @staticmethod
    def normalize_content(data: dict, domain: str) -> ExternalContent:
        def text(key):
            value = data.get(key)
            return value if isinstance(value, str) and value != "N/A" else None

        release = None
        if text("Released"):
            try:
                release = datetime.strptime(data["Released"], "%d %b %Y").date()
            except ValueError:
                release = None
        year = _number((text("Year") or "")[:4], int)
        runtime = _number((text("Runtime") or "").removesuffix(" min"), int)
        poster = text("Poster")
        meta = (
            {
                "director": text("Director"),
                "duration_minutes": runtime or None,
                "cast": _list(data.get("Actors"))[:6],
                "year": year,
            }
            if domain == "movies"
            else {"seasons": _number(text("totalSeasons") or "", int)}
        )
        return ExternalContent(
            provider="omdb",
            external_id=data["imdbID"],
            domain=domain,
            title=text("Title") or "",
            description=(text("Plot") or "")[:4000],
            cover_url=poster if poster and poster.startswith("https://") else None,
            release_date=release.isoformat() if release else None,
            genres=_list(data.get("Genre")),
            metadata={k: v for k, v in meta.items() if v not in (None, [])},
        )

    @staticmethod
    def normalize(data: dict) -> dict:
        imdb_id = data.get("imdbID")
        if not isinstance(imdb_id, str) or not IMDB_ID.match(imdb_id):
            raise ProviderError("Resposta externa inválida", 502)
        rotten = next(
            (
                r.get("Value")
                for r in data.get("Ratings") or []
                if r.get("Source") == "Rotten Tomatoes"
            ),
            None,
        )
        return {
            "imdb_id": imdb_id,
            "rating": _number(data.get("imdbRating"), float),
            "votes": _number(data.get("imdbVotes"), int),
            "metascore": _number(data.get("Metascore"), int),
            "rotten_tomatoes": rotten,
            "url": f"https://www.imdb.com/title/{imdb_id}/",
        }
