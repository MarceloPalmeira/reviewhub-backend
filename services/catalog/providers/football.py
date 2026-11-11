from datetime import UTC, datetime, timedelta

import httpx

from reviewhub_core.external import ExternalCatalogProvider, ExternalContent
from services.catalog.providers.base import ProviderError, RateGate, TTLCache, request

STAGES = {
    "REGULAR_SEASON": "",
    "GROUP_STAGE": "Fase de grupos",
    "LEAGUE_STAGE": "Fase de liga",
    "PRELIMINARY_ROUND": "Rodada preliminar",
    "QUALIFICATION": "Qualificação",
    "ROUND_1": "1ª fase",
    "ROUND_2": "2ª fase",
    "ROUND_3": "3ª fase",
    "PLAYOFFS": "Playoffs",
    "LAST_32": "16 avos de final",
    "LAST_16": "Oitavas de final",
    "QUARTER_FINALS": "Quartas de final",
    "SEMI_FINALS": "Semifinal",
    "THIRD_PLACE": "Disputa de 3º lugar",
    "FINAL": "Final",
}


COMPETITIONS = {
    "WC": "Copa do Mundo FIFA",
    "EC": "Eurocopa",
    "CL": "Liga dos Campeões da UEFA",
    "CLI": "Copa Libertadores",
    "BSA": "Brasileirão Série A",
    "PD": "La Liga",
    "SA": "Serie A Italiana",
}


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

    def competition_matches(self, code, season=None):
        """Partidas encerradas de uma competição; uma requisição por temporada."""
        if not code.isalnum() or not 2 <= len(code) <= 5:
            raise ProviderError("Código de competição inválido", 422)
        params = {"status": "FINISHED"}
        if season is not None:
            params["season"] = str(int(season))
        data = self.cache.get_or_load(
            ("competition", code.upper(), season),
            lambda: self._get(f"competitions/{code.upper()}/matches", params),
        )
        results = []
        for item in data.get("matches", []):
            if item.get("status") != "FINISHED" or not item.get("id"):
                continue
            item = {"competition": data.get("competition"), **item}
            try:
                results.append(self.normalize_content(item, "football_matches"))
            except ProviderError:
                continue
        return results

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
        competition = data.get("competition") or {}
        result = data.get("score") or {}
        score = dict(result.get("fullTime") or {})
        penalties = result.get("penalties") or {}
        if result.get("duration") == "PENALTY_SHOOTOUT" and penalties:
            # fullTime soma a disputa de pênaltis; o placar do jogo exclui.
            for side in ("home", "away"):
                if score.get(side) is not None and penalties.get(side) is not None:
                    score[side] -= penalties[side]
        meta = {
            "home_team": home,
            "away_team": away,
            "home_score": score.get("home"),
            "away_score": score.get("away"),
            "competition": COMPETITIONS.get(competition.get("code"))
            or competition.get("name")
            or "",
            "match_date": day,
            "status": data.get("status"),
            "season": (data.get("season") or {}).get("startDate"),
        }
        details = [meta["competition"], STAGES.get(data.get("stage"), "")]
        if data.get("matchday") and data.get("stage") == "REGULAR_SEASON":
            details.append(f"Rodada {data['matchday']}")
        if (data.get("group") or "").startswith("GROUP_"):
            details.append(f"Grupo {data['group'].removeprefix('GROUP_')}")
        description = " · ".join(part for part in details if part)
        if result.get("duration") == "EXTRA_TIME":
            description += ". Decidido na prorrogação."
        elif result.get("duration") == "PENALTY_SHOOTOUT" and penalties:
            description += (
                f". Pênaltis: {penalties.get('home')} × {penalties.get('away')}."
            )
        return ExternalContent(
            provider="football",
            external_id=str(data["id"]),
            domain=domain,
            title=f"{home} × {away}",
            description=description,
            release_date=day,
            metadata={k: v for k, v in meta.items() if v is not None},
        )
