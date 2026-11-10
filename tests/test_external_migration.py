"""A migration não deve perder conteúdos e listas anteriores."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def test_existing_catalog_survives_external_migration(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'catalog.db'}")
    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parents[1] / "services/catalog/migrations"),
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "b2138d3c1100")
        connection.execute(
            text(
                "INSERT INTO contents (id, domain, title, description, metadata_json, created_at) "
                "VALUES ('old', 'movies', 'Original', 'Descrição', '{}', '2024-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO custom_lists (id, owner_id, name, description, created_at) "
                "VALUES ('list', 'user', 'Minha lista', '', '2024-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO list_items (id, list_id, content_id) VALUES ('item', 'list', 'old')"
            )
        )
        command.upgrade(config, "head")
        assert connection.execute(
            text("SELECT title, external_provider FROM contents WHERE id='old'")
        ).one() == ("Original", None)
        assert (
            connection.execute(
                text("SELECT content_id FROM list_items WHERE list_id='list'")
            ).scalar_one()
            == "old"
        )
