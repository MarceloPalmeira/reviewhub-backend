from alembic import context

from services.catalog.main import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_online():
    connection = config.attributes["connection"]
    context.configure(
        connection=connection, target_metadata=target_metadata, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
