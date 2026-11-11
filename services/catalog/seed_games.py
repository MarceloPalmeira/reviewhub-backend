"""Popula o catálogo com games reais da IGDB.

O repositório guarda apenas os identificadores IGDB; nome, resumo, capa,
plataformas, gêneros e desenvolvedora são buscados a cada execução, em lotes
(uma requisição para até 100 jogos). Requer `IGDB_CLIENT_ID`,
`IGDB_CLIENT_SECRET` e rede. Idempotente: jogos já presentes são mantidos.

Uso: python -m services.catalog.seed_games
"""

import sys

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from reviewhub_core.plugins import FeatureRegistry
from services.catalog.main import Content, Session, engine
from services.catalog.providers.base import ProviderError
from services.catalog.providers.registry import configured_provider
from services.common import product
from services.migrations import migrate

GAME_IDS = [
    358,  # Super Mario Bros.
    1022,  # The Legend of Zelda
    8197,  # Tetris
    3186,  # Street Fighter II
    3192,  # Sonic the Hedgehog
    1070,  # Super Mario World
    1026,  # The Legend of Zelda: A Link to the Past
    673,  # Doom
    1802,  # Chrono Trigger
    1074,  # Super Mario 64
    427,  # Final Fantasy VII
    1638,  # GoldenEye 007
    1029,  # The Legend of Zelda: Ocarina of Time
    375,  # Metal Gear Solid
    231,  # Half-Life
    230,  # StarCraft
    974,  # Resident Evil 4
    481,  # Silent Hill 2
    733,  # Grand Theft Auto: Vice City
    732,  # Grand Theft Auto: San Andreas
    740,  # Halo: Combat Evolved
    2207,  # Shadow of the Colossus
    123,  # World of Warcraft
    233,  # Half-Life 2
    71,  # Portal
    72,  # Portal 2
    20,  # BioShock
    74,  # Mass Effect 2
    1077,  # Super Mario Galaxy
    434,  # Red Dead Redemption
    121,  # Minecraft: Java Edition
    472,  # The Elder Scrolls V: Skyrim
    2155,  # Dark Souls
    1352,  # Journey
    1009,  # The Last of Us
    1020,  # Grand Theft Auto V
    7334,  # Bloodborne
    1942,  # The Witcher 3: Wild Hunt
    12517,  # Undertale
    17000,  # Stardew Valley
    8173,  # Overwatch
    7342,  # Inside
    7346,  # The Legend of Zelda: Breath of the Wild
    26758,  # Super Mario Odyssey
    14593,  # Hollow Knight
    26226,  # Celeste
    19560,  # God of War
    25076,  # Red Dead Redemption 2
    90101,  # Super Smash Bros. Ultimate
    76882,  # Sekiro: Shadows Die Twice
    26472,  # Disco Elysium
    11737,  # Outer Wilds
    113112,  # Hades
    109462,  # Animal Crossing: New Horizons
    26192,  # The Last of Us Part II
    111469,  # Among Us
    1877,  # Cyberpunk 2077
    119133,  # Elden Ring
    119171,  # Baldur's Gate III
    119388,  # The Legend of Zelda: Tears of the Kingdom
    127044,  # Marvel's Spider-Man 2
    185246,  # Alan Wake II
    251833,  # Balatro
    303811,  # Astro Bot
    133236,  # Final Fantasy VII Rebirth
    136879,  # Black Myth: Wukong
    26602,  # Metaphor: ReFantazio
    191435,  # Animal Well
    90558,  # Satisfactory
    115,  # League of Legends
    1372,  # Counter-Strike: Global Offensive
    2963,  # Dota 2
    1905,  # Fortnite
    126459,  # Valorant
    11198,  # Rocket League
    1879,  # Terraria
    26764,  # Mario Kart 8 Deluxe
    36926,  # Monster Hunter: World
    19686,  # Resident Evil 2
    103298,  # Doom Eternal
    75235,  # Ghost of Tsushima
    135243,  # It Takes Two
    115289,  # Hollow Knight: Silksong
    325594,  # Split Fiction
    305152,  # Clair Obscur: Expedition 33
    298526,  # Kingdom Come: Deliverance II
    19564,  # Death Stranding
    9061,  # Cuphead
    37001,  # Ori and the Will of the Wisps
    26855,  # Dead Cells
    9643,  # Return of the Obra Dinn
    565,  # Uncharted 2: Among Thieves
    1105,  # Metroid Prime
    1219,  # Kingdom Hearts
    11156,  # Horizon Zero Dawn
    16,  # Fallout: New Vegas
    126,  # Diablo II
    223,  # The Sims
    327,  # Age of Empires II: The Age of Kings
    5614,  # Kentucky Route Zero
    1561,  # Pokémon Red Version
    112875,  # God of War Ragnarök
    114283,  # Persona 5 Royal
]
BATCH = 100


def main(provider=None, ids=GAME_IDS):
    config = product()
    domain = "video_games"
    if domain not in config.domains:
        print("O produto não habilita games; nada a fazer.")
        return 0
    if provider is None:
        provider = configured_provider("igdb")
        if provider is None:
            print(
                "Configure IGDB_CLIENT_ID e IGDB_CLIENT_SECRET para usar este seed.",
                file=sys.stderr,
            )
            return 1
    plugin = FeatureRegistry(config.domains).get(domain)
    migrate("catalog", engine)
    added = kept = failed = 0
    with Session() as db:
        existing = set(
            db.scalars(
                select(Content.external_id).where(
                    Content.external_provider == "igdb", Content.domain == domain
                )
            )
        )
        missing = [str(i) for i in ids if str(i) not in existing]
        kept = len(ids) - len(missing)
        for start in range(0, len(missing), BATCH):
            batch = missing[start : start + BATCH]
            try:
                games = provider.get_many(batch, domain)
            except ProviderError as exc:
                failed += len(batch)
                print(f"Lote {start // BATCH + 1}: {exc}", file=sys.stderr)
                continue
            found = {game.external_id: game for game in games}
            for igdb_id in batch:
                game = found.get(igdb_id)
                if game is None:
                    failed += 1
                    print(f"{igdb_id}: não encontrado na IGDB", file=sys.stderr)
                    continue
                try:
                    metadata = plugin.schema.model_validate(
                        plugin.visible_metadata(game.metadata, config.features)
                    ).model_dump(exclude_none=True, mode="json")
                except (ValidationError, ValueError) as exc:
                    failed += 1
                    print(f"{igdb_id}: {exc}", file=sys.stderr)
                    continue
                db.add(
                    Content(
                        id=f"igdb-{igdb_id}",
                        domain=domain,
                        title=game.title,
                        description=game.description,
                        metadata_json=metadata,
                        cover_url=game.cover_url,
                        release_date=game.release_date,
                        genres=game.genres,
                        external_provider="igdb",
                        external_id=igdb_id,
                    )
                )
                added += 1
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            print(
                "Outra execução gravou os mesmos itens; rode o comando novamente.",
                file=sys.stderr,
            )
            return 3
    print(f"Games: {added} adicionados, {kept} já existentes, {failed} falhas.")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
