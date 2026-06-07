"""add ingestion records

Revision ID: 20260328_0003
Revises: 20260328_0002
Create Date: 2026-03-28 02:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260328_0003"
down_revision: Union[str, None] = "20260328_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("source_listing_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("detail", sa.String(length=1000), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ingestion_records_id"), "ingestion_records", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ingestion_records_id"), table_name="ingestion_records")
    op.drop_table("ingestion_records")
