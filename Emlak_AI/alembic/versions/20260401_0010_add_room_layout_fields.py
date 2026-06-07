"""add room layout decomposition fields

Revision ID: 20260401_0010
Revises: 20260331_0009
Create Date: 2026-04-01 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260401_0010"
down_revision: Union[str, Sequence[str], None] = "20260331_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("room_layout_raw", sa.String(length=20), nullable=True))
    op.add_column("listings", sa.Column("room_count_main", sa.Integer(), nullable=True))
    op.add_column("listings", sa.Column("room_count_living", sa.Integer(), nullable=True))
    op.add_column("listings", sa.Column("room_count_total", sa.Integer(), nullable=True))

    op.execute("UPDATE listings SET room_count_main = room_count WHERE room_count_main IS NULL")
    op.execute("UPDATE listings SET room_count_total = room_count WHERE room_count_total IS NULL")


def downgrade() -> None:
    op.drop_column("listings", "room_count_total")
    op.drop_column("listings", "room_count_living")
    op.drop_column("listings", "room_count_main")
    op.drop_column("listings", "room_layout_raw")
