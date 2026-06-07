"""add user_recommendation_feedback table

Revision ID: 20260429_0019
Revises: 20260429_0018
Create Date: 2026-04-29 13:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260429_0019"
down_revision: Union[str, Sequence[str], None] = "20260429_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_recommendation_feedbacks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("liked", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("user_recommendation_feedbacks")