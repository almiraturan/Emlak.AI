"""initial schema

Revision ID: 20260328_0001
Revises:
Create Date: 2026-03-28 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260328_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "listings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("area_m2", sa.Float(), nullable=False),
        sa.Column("room_count", sa.Integer(), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("district", sa.String(length=100), nullable=False),
        sa.Column("neighborhood", sa.String(length=100), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("building_age", sa.Integer(), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=False),
        sa.Column("heating_type", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_listings_id"), "listings", ["id"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("budget_min", sa.Float(), nullable=False),
        sa.Column("budget_max", sa.Float(), nullable=False),
        sa.Column("preferred_rooms", sa.Integer(), nullable=False),
        sa.Column("prefers_quiet", sa.Boolean(), nullable=False),
        sa.Column("prefers_central", sa.Boolean(), nullable=False),
        sa.Column("purpose", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)

    op.create_table(
        "user_interactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("liked", sa.Boolean(), nullable=False),
        sa.Column("saved", sa.Boolean(), nullable=False),
        sa.Column("viewed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_interactions_id"), "user_interactions", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_interactions_id"), table_name="user_interactions")
    op.drop_table("user_interactions")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_listings_id"), table_name="listings")
    op.drop_table("listings")
