"""add listing lifecycle fields for ingestion runs

Revision ID: 20260401_0012
Revises: 20260401_0011
Create Date: 2026-04-01 14:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260401_0012"
down_revision: Union[str, Sequence[str], None] = "20260401_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("listings", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("listings", sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("listings", sa.Column("last_ingested_run_id", sa.String(length=64), nullable=True))

    op.execute(
        """
        UPDATE listings
        SET
            first_seen_at = COALESCE(first_seen_at, published_at, source_updated_at, NOW()),
            last_seen_at = COALESCE(last_seen_at, source_updated_at, published_at, NOW())
        """
    )


def downgrade() -> None:
    op.drop_column("listings", "last_ingested_run_id")
    op.drop_column("listings", "deactivated_at")
    op.drop_column("listings", "last_seen_at")
    op.drop_column("listings", "first_seen_at")
