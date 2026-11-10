"""Aplica as migrações próprias de um serviço ao banco configurado."""

from pathlib import Path

from alembic import command
from alembic.config import Config


def migrate(service, engine):
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).parent / service / "migrations")
    )
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
