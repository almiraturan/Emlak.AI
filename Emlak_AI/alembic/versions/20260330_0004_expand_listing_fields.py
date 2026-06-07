"""expand listing fields

Revision ID: 20260330_0004
Revises: 20260328_0003
Create Date: 2026-03-30 00:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260330_0004"
down_revision: Union[str, None] = "20260328_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Urun ihtiyaclari icin ilan tablosuna aciklama, tip, para birimi, medya ve zaman alanlari eklenir.
    op.add_column("listings", sa.Column("description", sa.String(length=5000), nullable=True))
    op.add_column(
        "listings",
        sa.Column("listing_type", sa.String(length=50), nullable=False, server_default="satilik"),
    )
    op.add_column(
        "listings",
        sa.Column("property_type", sa.String(length=50), nullable=False, server_default="daire"),
    )
    op.add_column(
        "listings",
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="TRY"),
    )
    op.add_column("listings", sa.Column("net_m2", sa.Float(), nullable=True))
    op.add_column("listings", sa.Column("gross_m2", sa.Float(), nullable=True))
    op.add_column(
        "listings",
        sa.Column("image_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "listings",
        sa.Column("images", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.add_column("listings", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("listings", sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "listings",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    # Mevcut kayitlar bos kalmasin diye temel bir backfill uygulanir.
    op.execute("UPDATE listings SET net_m2 = area_m2 * 0.88 WHERE net_m2 IS NULL")
    op.execute("UPDATE listings SET gross_m2 = area_m2 WHERE gross_m2 IS NULL")
    op.execute(
        "UPDATE listings SET description = CONCAT(district, ' ', neighborhood, ' bolgesinde yer alan ilan.') WHERE description IS NULL"
    )


def downgrade() -> None:
    op.drop_column("listings", "is_active")
    op.drop_column("listings", "source_updated_at")
    op.drop_column("listings", "published_at")
    op.drop_column("listings", "images")
    op.drop_column("listings", "image_count")
    op.drop_column("listings", "gross_m2")
    op.drop_column("listings", "net_m2")
    op.drop_column("listings", "currency")
    op.drop_column("listings", "property_type")
    op.drop_column("listings", "listing_type")
    op.drop_column("listings", "description")
