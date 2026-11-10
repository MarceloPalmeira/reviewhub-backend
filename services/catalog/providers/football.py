from datetime import UTC, datetime, timedelta

import httpx

from reviewhub_core.external import ExternalCatalogProvider, ExternalContent
from services.catalog.providers.base import ProviderError, RateGate, TTLCache, request


class FootballProvider(ExternalCatalogProvider):
    def __init__(self, token, client=None):
        self.token = token
        self.client = client or httpx.Client()
        self.gate = RateGate(6.2)
        self.cache = TTLCache(ttl=900)

    def _get(self, path, params=None):
        return self.gate.call(
            lambda: request(
                self.client,
                "GET",
                f"https://api.football-data.org/v4/{path}",
                params=params,
                headers={"X-Auth-Token": self.token},
            )
        )

    def search(self, query, domain, page=1):
        if domain != "football_matches":
            raise ProviderError("Domínio incompatível", 404)
        today = datetime.now(UTC).date()
        data = self.cache.get_or_load(
            ("matches", today.isoformat()),
            lambda: self._get(
                "matches",
                {
                    "status": "FINISHED",
                    "dateFrom": (today - timedelta(days=30)).isoformat(),
                    "dateTo": today.isoformat(),
                },
            ),
        )
        matches = [
            x
            for x in data.get("matches", [])
            if query.casefold()
            in f"{(x.get('homeTeam') or {}).get('name', '')} {(x.get('awayTeam') or {}).get('name', '')} {(x.get('competition') or {}).get('name', '')}".casefold()
        ]
        return [
            self.normalize_content(x, domain)
            for x in matches[(page - 1) * 20 : page * 20]
            if x.get("id") and x.get("homeTeam") and x.get("awayTeam")
        ]

    def get_details(self, external_id, domain):
        if domain != "football_matches" or not external_id.isdecimal():
            raise ProviderError("Identificador externo inválido", 422)
        data = self.cache.get_or_load(
            ("details", external_id), lambda: self._get(f"matches/{external_id}")
        )
        if data.get("status") != "FINISHED":
            raise ProviderError("Somente partidas concluídas podem ser importadas", 422)
        return self.normalize_content(data, domain)

    def normalize_content(self, data, domain):
        home = (data.get("homeTeam") or {}).get("name")
        away = (data.get("awayTeam") or {}).get("name")
        day = (data.get("utcDate") or "")[:10]
        if not home or not away or not day:
            raise ProviderError("Partida com dados incompletos", 422)
        score = (data.get("score") or {}).get("fullTime") or {}
        meta = {
            "home_team": home,
            "away_team": away,
            "home_score": score.get("home"),
            "away_score": score.get("away"),
            "competition": (data.get("competition") or {}).get("name") or "",
            "match_date": day,
            "status": data.get("status"),
            "season": (data.get("season") or {}).get("startDate"),
        }
        return ExternalContent(
            provider="football",
            external_id=str(data["id"]),
            domain=domain,
            title=f"{home} × {away}",
            description="",
            release_date=day,
            metadata={k: v for k, v in meta.items() if v is not None},
        )
