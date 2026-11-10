"""Dados fictícios idempotentes para os domínios habilitados."""

from services.catalog.local_dataset import LOCAL_CONTENT
from services.catalog.main import Content, Session, engine
from services.common import product
from services.migrations import migrate

SAMPLES = {
    "movies": (
        "A Última Estação",
        {
            "director": "Ana Lima",
            "duration_minutes": 105,
            "cast": ["Bia Luz"],
            "year": 2023,
        },
    ),
    "series": (
        "Ventos do Norte",
        {"seasons": 2, "episodes": 16, "status": "concluída"},
    ),
    "video_games": (
        "Ilhas de Vidro",
        {
            "platforms": ["PC"],
            "developer": "Estúdio Exemplo",
            "genre": "aventura",
            "year": 2024,
        },
    ),
    "football_matches": (
        "Azul FC × União Verde",
        {
            "home_team": "Azul FC",
            "away_team": "União Verde",
            "home_score": 2,
            "away_score": 1,
            "competition": "Copa Fictícia",
            "match_date": "2024-05-12",
        },
    ),
    "music_albums": (
        "Luzes da Cidade",
        {
            "artist": "Artista Fictício",
            "genre": "pop",
            "year": 2023,
            "tracks": ["Primeira Luz", "Noite Clara"],
        },
    ),
}


def main():
    migrate("catalog", engine)
    with Session() as db:
        for domain in product().domains:
            if domain not in SAMPLES:
                continue
            identifier = f"demo-{domain}"
            if db.get(Content, identifier) is None:
                title, metadata = SAMPLES[domain]
                db.add(
                    Content(
                        id=identifier,
                        domain=domain,
                        title=title,
                        description="Conteúdo fictício para demonstração.",
                        metadata_json=metadata,
                    )
                )
        for domain in product().domains:
            for slug, title, metadata in LOCAL_CONTENT.get(domain, []):
                identifier = f"local-{domain}-{slug}"
                if db.get(Content, identifier) is None:
                    db.add(
                        Content(
                            id=identifier,
                            domain=domain,
                            title=title,
                            description="",
                            metadata_json=metadata,
                        )
                    )
        db.commit()
    print("Dados de demonstração disponíveis.")


if __name__ == "__main__":
    main()
