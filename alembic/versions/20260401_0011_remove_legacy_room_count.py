"""remove legacy room_count column and enforce room_count_total

Revision ID: 20260401_0011
Revises: 20260401_0010
Create Date: 2026-04-01 13:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260401_0011"
down_revision: Union[str, Sequence[str], None] = "20260401_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE listings
        SET room_count_total = COALESCE(room_count_total, room_count, room_count_main)
        """
    )

    op.alter_column("listings", "room_count_total", existing_type=sa.Integer(), nullable=False)
    op.drop_column("listings", "room_count")


def downgrade() -> None:
    op.add_column("listings", sa.Column("room_count", sa.Integer(), nullable=True))
    op.execute("UPDATE listings SET room_count = COALESCE(room_count_total, room_count_main, 0)")
    op.alter_column("listings", "room_count", existing_type=sa.Integer(), nullable=False)
    op.alter_column("listings", "room_count_total", existing_type=sa.Integer(), nullable=True)
