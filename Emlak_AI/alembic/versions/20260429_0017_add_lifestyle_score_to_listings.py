"""add lifestyle_score to listings

Revision ID: 20260429_0017
Revises: 20260429_0016
Create Date: 2026-04-29 11:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260429_0017"
down_revision: Union[str, Sequence[str], None] = "20260429_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("lifestyle_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "lifestyle_score")