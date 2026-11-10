"""Identidade externa e metadados opcionais sem alterar registros existentes."""

import sqlalchemy as sa
from alembic import op

revision = "c3e29f7d40b2"
down_revision = "b2138d3c1100"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "contents", sa.Column("external_provider", sa.String(32), nullable=True)
    )
    op.add_column("contents", sa.Column("external_id", sa.String(100), nullable=True))
    op.add_column("contents", sa.Column("backdrop_url", sa.String(), nullable=True))
    op.add_column("contents", sa.Column("release_date", sa.String(32), nullable=True))
    op.add_column("contents", sa.Column("genres", sa.JSON(), nullable=True))
    op.create_index(
        "uq_content_external_identity",
        "contents",
        ["external_provider", "domain", "external_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("uq_content_external_identity", table_name="contents")
    for column in (
        "genres",
        "release_date",
        "backdrop_url",
        "external_id",
        "external_provider",
    ):
        op.drop_column("contents", column)
