"""create listing_images table and backfill from listings.images

Revision ID: 20260401_0013
Revises: 20260401_0012
Create Date: 2026-04-01 15:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260401_0013"
down_revision: Union[str, Sequence[str], None] = "20260401_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "listing_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_cover", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("file_hash", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_listing_images_id", "listing_images", ["id"], unique=False)
    op.create_index("ix_listing_images_listing_id", "listing_images", ["listing_id"], unique=False)
    op.create_unique_constraint(
        "uq_listing_images_listing_id_order_index",
        "listing_images",
        ["listing_id", "order_index"],
    )

    op.execute(
        """
        INSERT INTO listing_images (listing_id, url, order_index, is_cover, status)
        SELECT
            l.id AS listing_id,
            img.url AS url,
            img.ord - 1 AS order_index,
            (img.ord = 1) AS is_cover,
            'active' AS status
        FROM listings l
        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(l.images::jsonb, '[]'::jsonb)) WITH ORDINALITY AS img(url, ord)
        """
    )


def downgrade() -> None:
    op.drop_constraint("uq_listing_images_listing_id_order_index", "listing_images", type_="unique")
    op.drop_index("ix_listing_images_listing_id", table_name="listing_images")
    op.drop_index("ix_listing_images_id", table_name="listing_images")
    op.drop_table("listing_images")
