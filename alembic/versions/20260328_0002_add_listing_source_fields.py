"""add listing source fields

Revision ID: 20260328_0002
Revises: 20260328_0001
Create Date: 2026-03-28 01:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260328_0002"
down_revision: Union[str, None] = "20260328_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Dis kaynaktan gelen veriyi takip edebilmek icin kaynak kolonlari eklenir.
    op.add_column("listings", sa.Column("source", sa.String(length=100), nullable=True))
    op.add_column("listings", sa.Column("source_listing_id", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("source_url", sa.String(length=1000), nullable=True))

    # Mevcut seed kayitlarin yeni yapida bos kalmamasi icin geriye donuk doldurma yapilir.
    op.execute("UPDATE listings SET source = 'seed' WHERE source IS NULL")
    op.execute("UPDATE listings SET source_listing_id = CAST(id AS TEXT) WHERE source_listing_id IS NULL")

    # Ayni kaynaktan gelen ayni ilan ikinci kez ayri satir olarak yazilamasin diye benzersizlik eklenir.
    op.create_unique_constraint(
        "uq_listings_source_source_listing_id",
        "listings",
        ["source", "source_listing_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_listings_source_source_listing_id", "listings", type_="unique")
    op.drop_column("listings", "source_url")
    op.drop_column("listings", "source_listing_id")
    op.drop_column("listings", "source")
