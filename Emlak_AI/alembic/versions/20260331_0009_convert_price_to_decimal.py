"""convert price columns to numeric decimal

Revision ID: 20260331_0009
Revises: 20260330_0008
Create Date: 2026-03-31 10:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260331_0009"
down_revision: Union[str, None] = "20260330_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fiyat alanlari hassas hesaplama icin Numeric(14,2) tipine cevrilildi.
    # Float'tan Decimal'a gecis yapildi; finansal acudan daha guvenclidir.
    
    # Oncesinde eski NULL'tan kacmak icin default'lar set edilir
    # (mevcut veri zaten dolu oldugundan skip edilebilir)
    
    op.alter_column(
        "listings",
        "price",
        existing_type=sa.Float(),
        type_=sa.Numeric(precision=14, scale=2),
        existing_nullable=False,
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "listings",
        "price",
        existing_type=sa.Numeric(precision=14, scale=2),
        type_=sa.Float(),
        existing_nullable=False,
        nullable=False,
    )
