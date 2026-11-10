"""Add private user lists to catalog."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2138d3c1100"
down_revision: str | Sequence[str] | None = "ae22f4f1fb13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "custom_lists",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_custom_lists_owner_id", "custom_lists", ["owner_id"])
    op.create_table(
        "list_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "list_id",
            sa.String(),
            sa.ForeignKey("custom_lists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "content_id",
            sa.String(),
            sa.ForeignKey("contents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("list_id", "content_id"),
    )
    op.create_index("ix_list_items_list_id", "list_items", ["list_id"])


def downgrade() -> None:
    op.drop_index("ix_list_items_list_id", table_name="list_items")
    op.drop_table("list_items")
    op.drop_index("ix_custom_lists_owner_id", table_name="custom_lists")
    op.drop_table("custom_lists")
