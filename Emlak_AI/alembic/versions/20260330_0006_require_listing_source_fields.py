"""require listing source fields

Revision ID: 20260330_0006
Revises: 20260330_0005
Create Date: 2026-03-30 01:40:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260330_0006"
down_revision: Union[str, None] = "20260330_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guvenlik icin NULL kalmis kayitlar once geri doldurulur.
    op.execute("UPDATE listings SET source = 'unknown' WHERE source IS NULL")
    op.execute("UPDATE listings SET source_listing_id = id::text WHERE source_listing_id IS NULL")

    op.alter_column(
        "listings",
        "source",
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.alter_column(
        "listings",
        "source_listing_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "listings",
        "source_listing_id",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.alter_column(
        "listings",
        "source",
        existing_type=sa.String(length=100),
        nullable=True,
    )
