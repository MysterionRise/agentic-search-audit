"""Initial migration - create all tables

Revision ID: 10b7cb21af22
Revises:
Create Date: 2026-02-04 01:35:26.139727

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "10b7cb21af22"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all tables."""
    # Organizations table
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, default=True, nullable=False),
        sa.Column("is_admin", sa.Boolean, default=False, nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    # API Keys table
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("prefix", sa.String(8), nullable=False, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Audits table
    op.create_table(
        "audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
        sa.Column("site_url", sa.String(2048), nullable=False),
        sa.Column("queries", postgresql.JSON, nullable=False),
        sa.Column("config_override", postgresql.JSON, nullable=True),
        sa.Column("headless", sa.Boolean, default=True, nullable=False),
        sa.Column("top_k", sa.Integer, default=10, nullable=False),
        sa.Column("webhook_url", sa.String(2048), nullable=True),
        sa.Column("status", sa.String(20), default="pending", nullable=False),
        sa.Column("completed_queries", sa.Integer, default=0, nullable=False),
        sa.Column("average_score", sa.Float, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create indexes for audits
    op.create_index("ix_audits_user_created", "audits", ["user_id", "created_at"])
    op.create_index("ix_audits_status", "audits", ["status"])

    # Audit Results table
    op.create_table(
        "audit_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "audit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("audits.id"),
            nullable=False,
        ),
        sa.Column("query_text", sa.String(1000), nullable=False),
        sa.Column("query_data", postgresql.JSON, nullable=False),
        sa.Column("items", postgresql.JSON, nullable=False),
        sa.Column("score", postgresql.JSON, nullable=False),
        sa.Column("screenshot_path", sa.String(500), nullable=True),
        sa.Column("html_path", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Audit Reports table
    op.create_table(
        "audit_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "audit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("audits.id"),
            nullable=False,
        ),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Usage Records table
    op.create_table(
        "usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("audit_count", sa.Integer, default=0, nullable=False),
        sa.Column("query_count", sa.Integer, default=0, nullable=False),
        sa.Column("llm_tokens_used", sa.Integer, default=0, nullable=False),
    )

    # Create index for usage records
    op.create_index("ix_usage_user_period", "usage_records", ["user_id", "period_start"])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_index("ix_usage_user_period", table_name="usage_records")
    op.drop_table("usage_records")
    op.drop_table("audit_reports")
    op.drop_table("audit_results")
    op.drop_index("ix_audits_status", table_name="audits")
    op.drop_index("ix_audits_user_created", table_name="audits")
    op.drop_table("audits")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.drop_table("organizations")
