"""Add email notification tables."""
from alembic import op
import sqlalchemy as sa


revision = "20260515_0020"
down_revision = "20260429_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_email_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subscribed", sa.Boolean(), default=True),
        sa.Column("min_lifestyle_score", sa.Integer(), default=8),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_notification_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_email_preferences_email", "user_email_preferences", ["email"], unique=True)
    op.create_index("ix_user_email_preferences_user_id", "user_email_preferences", ["user_id"])

    op.create_table(
        "listing_notifications_sent",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("user_email", sa.String(255), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_listing_notifications_sent_listing_id", "listing_notifications_sent", ["listing_id"])
    op.create_index("ix_listing_notifications_sent_user_email", "listing_notifications_sent", ["user_email"])


def downgrade() -> None:
    op.drop_index("ix_listing_notifications_sent_user_email", "listing_notifications_sent")
    op.drop_index("ix_listing_notifications_sent_listing_id", "listing_notifications_sent")
    op.drop_table("listing_notifications_sent")

    op.drop_index("ix_user_email_preferences_user_id", "user_email_preferences")
    op.drop_index("ix_user_email_preferences_email", "user_email_preferences")
    op.drop_table("user_email_preferences")
