"""add unique source constraint

Revision ID: 20260330_0008
Revises: 20260330_0007
Create Date: 2026-03-30 10:05:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260330_0008"
down_revision: Union[str, None] = "20260330_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ayni source + source_listing_id kombinasyonu birden fazla kez girmemeli.
    # Bolece ingestion race condition'unda bile duplicate ilan girilmesi engellenir.
    # (ORM kontrol ediyor ama DB garantisi de gerekli)
    op.create_unique_constraint(
        "uq_listings_source_and_source_listing_id",
        "listings",
        ["source", "source_listing_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_listings_source_and_source_listing_id",
        "listings",
        type_="unique",
    )
