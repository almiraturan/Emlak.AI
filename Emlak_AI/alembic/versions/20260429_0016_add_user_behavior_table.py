"""add user_behavior table

Revision ID: 20260429_0016
Revises: 20260402_0015
Create Date: 2026-04-29 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260429_0016"
down_revision: Union[str, Sequence[str], None] = "20260402_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_behaviors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("behavior_type", sa.String(length=20), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_behaviors_user_id", "user_behaviors", ["user_id"], unique=False)
    op.create_index("ix_user_behaviors_listing_id", "user_behaviors", ["listing_id"], unique=False)
    op.create_index("ix_user_behaviors_behavior_type", "user_behaviors", ["behavior_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_behaviors_behavior_type", table_name="user_behaviors")
    op.drop_index("ix_user_behaviors_listing_id", table_name="user_behaviors")
    op.drop_index("ix_user_behaviors_user_id", table_name="user_behaviors")
    op.drop_table("user_behaviors")