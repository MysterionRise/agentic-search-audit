"""Add stripe_customer_id and plan_id columns to users

Revision ID: a1b2c3d4e5f6
Revises: 10b7cb21af22
Create Date: 2026-02-20 19:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "10b7cb21af22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add billing columns to users table."""
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("plan_id", sa.String(50), nullable=True))


def downgrade() -> None:
    """Remove billing columns from users table."""
    op.drop_column("users", "plan_id")
    op.drop_column("users", "stripe_customer_id")
