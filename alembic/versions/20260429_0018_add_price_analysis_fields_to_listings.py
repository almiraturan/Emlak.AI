"""add price analysis fields to listings

Revision ID: 20260429_0018
Revises: 20260429_0017
Create Date: 2026-04-29 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260429_0018"
down_revision: Union[str, Sequence[str], None] = "20260429_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("price_market_avg", sa.Float(), nullable=True))
    op.add_column("listings", sa.Column("price_verdict", sa.String(length=20), nullable=True))
    op.add_column("listings", sa.Column("price_trend_direction", sa.String(length=10), nullable=True))
    op.add_column("listings", sa.Column("price_comparables_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "price_comparables_count")
    op.drop_column("listings", "price_trend_direction")
    op.drop_column("listings", "price_verdict")
    op.drop_column("listings", "price_market_avg")