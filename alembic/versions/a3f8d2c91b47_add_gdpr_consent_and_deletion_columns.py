"""Add GDPR consent and deletion columns to users

Revision ID: a3f8d2c91b47
Revises: 10b7cb21af22
Create Date: 2026-02-20 19:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f8d2c91b47"
down_revision: str | Sequence[str] | None = "10b7cb21af22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add GDPR consent and deletion columns to users table."""
    op.add_column(
        "users",
        sa.Column("consent_marketing", sa.Boolean, server_default="false", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("consent_analytics", sa.Boolean, server_default="true", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("consent_third_party", sa.Boolean, server_default="false", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("consent_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("deletion_scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("deletion_reason", sa.Text, nullable=True),
    )


def downgrade() -> None:
    """Remove GDPR consent and deletion columns from users table."""
    op.drop_column("users", "deletion_reason")
    op.drop_column("users", "deletion_scheduled_at")
    op.drop_column("users", "consent_updated_at")
    op.drop_column("users", "consent_third_party")
    op.drop_column("users", "consent_analytics")
    op.drop_column("users", "consent_marketing")
