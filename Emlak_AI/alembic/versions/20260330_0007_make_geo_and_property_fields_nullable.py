"""make geo and property fields nullable

Revision ID: 20260330_0007
Revises: 20260330_0006
Create Date: 2026-03-30 10:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260330_0007"
down_revision: Union[str, None] = "20260330_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Geo koordinatlari ve property-specific alanlar bazen eksik gelebilir.
    # Orn: Arsa icin building_age/floor/heating_type meaningless.
    #      Ticari alan icin geo koordinat olmayabilir.
    # Bu kolonlar nullable yapilir; backfill gerekli degil (mevcut veride full doldulu).
    
    op.alter_column(
        "listings",
        "latitude",
        existing_type=sa.Float(),
        nullable=True,
    )
    op.alter_column(
        "listings",
        "longitude",
        existing_type=sa.Float(),
        nullable=True,
    )
    op.alter_column(
        "listings",
        "building_age",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "listings",
        "floor",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "listings",
        "heating_type",
        existing_type=sa.String(length=100),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "listings",
        "heating_type",
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.alter_column(
        "listings",
        "floor",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "listings",
        "building_age",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "listings",
        "longitude",
        existing_type=sa.Float(),
        nullable=False,
    )
    op.alter_column(
        "listings",
        "latitude",
        existing_type=sa.Float(),
        nullable=False,
    )
