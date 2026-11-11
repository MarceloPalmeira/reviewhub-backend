"""Popula o catálogo com partidas reais do football-data.org.

Busca todas as partidas encerradas das competições e temporadas escolhidas
(uma requisição por temporada). Requer `FOOTBALL_DATA_API_TOKEN` e rede.
Idempotente: partidas já presentes são mantidas; repetir o comando durante uma
temporada em andamento adiciona apenas os jogos novos.

Uso:
    python -m services.catalog.seed_football               # padrão abaixo
    python -m services.catalog.seed_football BSA:2025 CL   # competição[:ano]
"""

import os
import sys

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from reviewhub_core.plugins import FeatureRegistry
from services.catalog.main import Content, Session, engine
from services.catalog.providers.base import ProviderError
from services.catalog.providers.football import FootballProvider
from services.common import product
from services.migrations import migrate

# Copa do Mundo 2026 completa e Brasileirão da temporada atual.
DEFAULT_SEASONS = [("WC", 2026), ("BSA", None)]


def parse(args):
    seasons = []
    for arg in args:
        code, _, year = arg.partition(":")
        seasons.append((code.upper(), int(year) if year else None))
    return seasons or DEFAULT_SEASONS


def main(provider=None, seasons=None):
    config = product()
    domain = "football_matches"
    if domain not in config.domains:
        print("O produto não habilita partidas de futebol; nada a fazer.")
        return 0
    if provider is None:
        token = os.getenv("FOOTBALL_DATA_API_TOKEN")
        if not token:
            print(
                "Configure FOOTBALL_DATA_API_TOKEN para usar este seed.",
                file=sys.stderr,
            )
            return 1
        provider = FootballProvider(token)
    plugin = FeatureRegistry(config.domains).get(domain)
    migrate("catalog", engine)
    added = kept = failed = 0
    with Session() as db:
        existing = set(
            db.scalars(
                select(Content.external_id).where(
                    Content.external_provider == "football", Content.domain == domain
                )
            )
        )
        for code, season in seasons or DEFAULT_SEASONS:
            label = f"{code}:{season or 'atual'}"
            try:
                matches = provider.competition_matches(code, season)
            except ProviderError as exc:
                failed += 1
                print(f"{label}: {exc}", file=sys.stderr)
                continue
            for match in matches:
                if match.external_id in existing:
                    kept += 1
                    continue
                try:
                    metadata = plugin.schema.model_validate(
                        plugin.visible_metadata(match.metadata, config.features)
                    ).model_dump(exclude_none=True, mode="json")
                except (ValidationError, ValueError) as exc:
                    failed += 1
                    print(f"{label} {match.external_id}: {exc}", file=sys.stderr)
                    continue
                db.add(
                    Content(
                        id=f"football-{match.external_id}",
                        domain=domain,
                        title=match.title,
                        description=match.description,
                        metadata_json=metadata,
                        release_date=match.release_date,
                        genres=[],
                        external_provider="football",
                        external_id=match.external_id,
                    )
                )
                existing.add(match.external_id)
                added += 1
            print(f"{label}: {len(matches)} partidas encerradas")
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            print(
                "Outra execução gravou os mesmos itens; rode o comando novamente.",
                file=sys.stderr,
            )
            return 3
    print(f"Partidas: {added} adicionadas, {kept} já existentes, {failed} falhas.")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main(seasons=parse(sys.argv[1:])))
