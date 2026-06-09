"""Add password and location fields to users."""
from alembic import op
import sqlalchemy as sa


revision = "20260608_0021"
down_revision = "20260515_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password", sa.String(length=100), nullable=False, server_default="12345"))
    op.add_column("users", sa.Column("province", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("district", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "district")
    op.drop_column("users", "province")
    op.drop_column("users", "password")
