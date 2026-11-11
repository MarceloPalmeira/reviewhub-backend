from datetime import date

import httpx

from reviewhub_core.external import ExternalCatalogProvider, ExternalContent
from services.catalog.providers.base import ProviderError, RateGate, TTLCache, request


class TMDBProvider(ExternalCatalogProvider):
    def __init__(self, token: str, client=None):
        self.token = token
        self.client = client or httpx.Client()
        self.gate = RateGate(0.25)
        self.cache = TTLCache(ttl=600)

    def _get(self, path, params=None):
        return self.gate.call(
            lambda: request(
                self.client,
                "GET",
                f"https://api.themoviedb.org/3/{path}",
                params={"language": "pt-BR", **(params or {})},
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                },
            )
        )

    def search(self, query, domain, page=1):
        kind = self._kind(domain)
        data = self.cache.get_or_load(
            ("search", domain, query.casefold(), page),
            lambda: self._get(
                f"search/{kind}",
                {"query": query, "page": page, "include_adult": "false"},
            ),
        )
        return [
            self.normalize_content(item, domain)
            for item in data.get("results", [])
            if item.get("id") and (item.get("title") or item.get("name"))
        ]

    def get_details(self, external_id, domain):
        if not external_id.isdecimal():
            raise ProviderError("Identificador externo inválido", 422)
        kind = self._kind(domain)
        data = self.cache.get_or_load(
            ("details", domain, external_id),
            lambda: self._get(
                f"{kind}/{external_id}", {"append_to_response": "credits"}
            ),
        )
        return self.normalize_content(data, domain)

    def imdb_id(self, external_id, domain):
        if not external_id.isdecimal():
            raise ProviderError("Identificador externo inválido", 422)
        kind = self._kind(domain)
        data = self.cache.get_or_load(
            ("external_ids", domain, external_id),
            lambda: self._get(f"{kind}/{external_id}/external_ids"),
        )
        value = data.get("imdb_id")
        return value if isinstance(value, str) and value.startswith("tt") else None

    @staticmethod
    def _kind(domain):
        if domain not in ("movies", "series"):
            raise ProviderError("Domínio incompatível com o provedor", 404)
        return "movie" if domain == "movies" else "tv"

    def normalize_content(self, data, domain):
        self._kind(domain)
        release = data.get("release_date") or data.get("first_air_date") or None
        year = None
        try:
            year = date.fromisoformat(release).year if release else None
        except (TypeError, ValueError):
            release = None
        credits = data.get("credits") or {}
        cast = [p.get("name") for p in credits.get("cast", [])[:6] if p.get("name")]
        director = next(
            (
                p.get("name")
                for p in credits.get("crew", [])
                if p.get("job") == "Director" and p.get("name")
            ),
            None,
        )
        if domain == "movies":
            meta = {
                "director": director,
                "duration_minutes": data.get("runtime") or None,
                "cast": cast,
                "year": year,
            }
        else:
            meta = {
                "seasons": data.get("number_of_seasons"),
                "episodes": data.get("number_of_episodes"),
                "status": data.get("status"),
            }

        def image(path, size):
            return (
                f"https://image.tmdb.org/t/p/{size}{path}"
                if isinstance(path, str) and path.startswith("/")
                else None
            )

        return ExternalContent(
            provider="tmdb",
            external_id=str(data["id"]),
            domain=domain,
            title=data.get("title") or data.get("name") or "",
            description=(data.get("overview") or "")[:4000],
            cover_url=image(data.get("poster_path"), "w500"),
            backdrop_url=image(data.get("backdrop_path"), "w1280"),
            release_date=release,
            genres=[x["name"] for x in data.get("genres", []) if x.get("name")],
            metadata={k: v for k, v in meta.items() if v is not None},
        )
