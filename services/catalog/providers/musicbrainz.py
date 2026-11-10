import threading
import time
from uuid import UUID

import httpx

from reviewhub_core.external import ExternalCatalogProvider, ExternalContent
from services.catalog.providers.base import ProviderError, TTLCache, request

_lock = threading.Lock()
_last_request = 0.0


class MusicBrainzProvider(ExternalCatalogProvider):
    def __init__(self, user_agent, client=None):
        self.client = client or httpx.Client()
        self.user_agent = user_agent
        self.cache = TTLCache(ttl=3600)

    def _get(self, path, params):
        global _last_request
        with _lock:
            delay = 1.1 - (time.monotonic() - _last_request)
            if delay > 0:
                time.sleep(delay)
            try:
                return request(
                    self.client,
                    "GET",
                    f"https://musicbrainz.org/ws/2/{path}",
                    params={"fmt": "json", **params},
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": "application/json",
                    },
                )
            finally:
                _last_request = time.monotonic()

    def search(self, query, domain, page=1):
        if domain != "music_albums":
            raise ProviderError("Domínio incompatível", 404)
        data = self.cache.get_or_load(
            ("search", query.casefold(), page),
            lambda: self._get(
                "release-group/",
                {"query": query, "limit": 20, "offset": (page - 1) * 20},
            ),
        )
        return [
            self.normalize_content(x, domain)
            for x in data.get("release-groups", [])
            if x.get("id") and x.get("title") and x.get("primary-type") == "Album"
        ]

    def get_details(self, external_id, domain):
        try:
            identifier = str(UUID(external_id))
        except ValueError as exc:
            raise ProviderError("Identificador externo inválido", 422) from exc
        if domain != "music_albums":
            raise ProviderError("Domínio incompatível", 404)

        def fetch():
            group = self._get(
                f"release-group/{identifier}", {"inc": "artist-credits+genres+releases"}
            )
            if group.get("primary-type") != "Album":
                raise ProviderError("O lançamento não é um álbum", 422)
            releases = group.get("releases", [])
            selected = next(
                (x for x in releases if x.get("status") == "Official"), None
            )
            if selected:
                try:
                    group["selected_release"] = self._get(
                        f"release/{selected['id']}", {"inc": "recordings"}
                    )
                except ProviderError:
                    pass
            return group

        return self.normalize_content(
            self.cache.get_or_load(("details", identifier), fetch), domain
        )

    def normalize_content(self, data, domain):
        credits = data.get("artist-credit", [])
        artist = "".join(
            x
            if isinstance(x, str)
            else (x.get("name") or x.get("artist", {}).get("name", ""))
            + x.get("joinphrase", "")
            for x in credits
        ).strip()
        genres = [x["name"] for x in data.get("genres", []) if x.get("name")]
        release = data.get("first-release-date") or None
        year = int(release[:4]) if release and release[:4].isdigit() else None
        tracks = [
            track.get("title") or track.get("recording", {}).get("title")
            for medium in (data.get("selected_release") or {}).get("media", [])
            for track in medium.get("tracks", [])
        ]
        metadata = {
            "artist": artist or None,
            "genre": ", ".join(genres) or None,
            "year": year,
            "tracks": [t for t in tracks if t] or None,
        }
        return ExternalContent(
            provider="musicbrainz",
            external_id=str(data["id"]),
            domain=domain,
            title=data["title"],
            description=data.get("disambiguation") or "",
            cover_url=f"https://coverartarchive.org/release-group/{data['id']}/front-500",
            release_date=release,
            genres=genres,
            metadata={k: v for k, v in metadata.items() if v is not None},
        )
