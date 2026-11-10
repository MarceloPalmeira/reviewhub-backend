import json
import threading
import time
from datetime import UTC, datetime

import httpx

from reviewhub_core.external import ExternalCatalogProvider, ExternalContent
from services.catalog.providers.base import ProviderError, RateGate, TTLCache, request

FIELDS = "name,summary,first_release_date,cover.image_id,platforms.name,genres.name,involved_companies.developer,involved_companies.company.name"


class IGDBProvider(ExternalCatalogProvider):
    def __init__(self, client_id, client_secret, client=None):
        self.client_id, self.client_secret = client_id, client_secret
        self.client = client or httpx.Client()
        self.gate = RateGate(0.3)
        self.cache = TTLCache(ttl=600)
        self.token = None
        self.expires = 0.0
        self.lock = threading.Lock()

    def _token(self):
        with self.lock:
            if not self.token or time.monotonic() >= self.expires:
                data = request(
                    self.client,
                    "POST",
                    "https://id.twitch.tv/oauth2/token",
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": "client_credentials",
                    },
                )
                if not data.get("access_token"):
                    raise ProviderError("Autenticação do provedor indisponível")
                self.token = data["access_token"]
                self.expires = time.monotonic() + max(
                    0, int(data.get("expires_in", 0)) - 60
                )
            return self.token

    def _games(self, query):
        def perform():
            token = self._token()
            return request(
                self.client,
                "POST",
                "https://api.igdb.com/v4/games",
                content=query,
                headers={
                    "Client-ID": self.client_id,
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "text/plain",
                },
            )

        try:
            return self.gate.call(perform)
        except ProviderError as exc:
            if exc.upstream_status != 401:
                raise
            with self.lock:
                self.token = None
                self.expires = 0.0
            return self.gate.call(perform)

    def search(self, query, domain, page=1):
        if domain != "video_games":
            raise ProviderError("Domínio incompatível", 404)
        text = f"search {json.dumps(query)}; fields {FIELDS}; limit 20; offset {(page - 1) * 20};"
        data = self.cache.get_or_load(
            ("search", query.casefold(), page), lambda: self._games(text)
        )
        return [
            self.normalize_content(x, domain)
            for x in data
            if x.get("id") and x.get("name")
        ]

    def get_details(self, external_id, domain):
        if domain != "video_games" or not external_id.isdecimal():
            raise ProviderError("Identificador externo inválido", 422)
        data = self.cache.get_or_load(
            ("details", external_id),
            lambda: self._games(f"fields {FIELDS}; where id = {external_id}; limit 1;"),
        )
        if not data:
            raise ProviderError("Conteúdo externo não encontrado", 404)
        return self.normalize_content(data[0], domain)

    def normalize_content(self, data, domain):
        release = None
        try:
            if data.get("first_release_date") is not None:
                release = (
                    datetime.fromtimestamp(data["first_release_date"], UTC)
                    .date()
                    .isoformat()
                )
        except (ValueError, OSError, OverflowError, TypeError):
            pass
        companies = data.get("involved_companies") or []
        developer = next(
            (
                c.get("company", {}).get("name")
                for c in companies
                if c.get("developer")
                and isinstance(c.get("company"), dict)
                and c["company"].get("name")
            ),
            None,
        )
        platforms = [
            x["name"]
            for x in data.get("platforms", [])
            if isinstance(x, dict) and x.get("name")
        ]
        genres = [
            x["name"]
            for x in data.get("genres", [])
            if isinstance(x, dict) and x.get("name")
        ]
        image_id = (data.get("cover") or {}).get("image_id", "")
        cover = (
            f"https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg"
            if image_id.isalnum()
            else None
        )
        meta = {
            "platforms": platforms or None,
            "developer": developer,
            "genre": ", ".join(genres) or None,
            "year": int(release[:4]) if release else None,
        }
        return ExternalContent(
            provider="igdb",
            external_id=str(data["id"]),
            domain=domain,
            title=data["name"],
            description=(data.get("summary") or "")[:4000],
            cover_url=cover,
            release_date=release,
            genres=genres,
            metadata={k: v for k, v in meta.items() if v is not None},
        )
