"""add canonical location fields to listings

Revision ID: 20260401_0014
Revises: 20260401_0013
Create Date: 2026-04-01 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260401_0014"
down_revision: Union[str, Sequence[str], None] = "20260401_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("city_canonical", sa.String(length=100), nullable=True))
    op.add_column("listings", sa.Column("district_canonical", sa.String(length=100), nullable=True))
    op.add_column("listings", sa.Column("neighborhood_canonical", sa.String(length=100), nullable=True))

    op.execute(
        """
        UPDATE listings
        SET
            city_canonical = TRIM(REGEXP_REPLACE(LOWER(TRANSLATE(COALESCE(city, ''), 'ÇĞİIÖŞÜçğıöşü', 'CGIIOSUcgiosu')), '\\s+', ' ', 'g')),
            district_canonical = TRIM(REGEXP_REPLACE(LOWER(TRANSLATE(COALESCE(district, ''), 'ÇĞİIÖŞÜçğıöşü', 'CGIIOSUcgiosu')), '\\s+', ' ', 'g')),
            neighborhood_canonical = TRIM(REGEXP_REPLACE(LOWER(TRANSLATE(COALESCE(neighborhood, ''), 'ÇĞİIÖŞÜçğıöşü', 'CGIIOSUcgiosu')), '\\s+', ' ', 'g'))
        """
    )


def downgrade() -> None:
    op.drop_column("listings", "neighborhood_canonical")
    op.drop_column("listings", "district_canonical")
    op.drop_column("listings", "city_canonical")
