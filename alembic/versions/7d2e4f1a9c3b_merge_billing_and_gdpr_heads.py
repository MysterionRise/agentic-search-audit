"""Merge the billing and GDPR branches

Revision ID: 7d2e4f1a9c3b
Revises: a1b2c3d4e5f6, a3f8d2c91b47
Create Date: 2026-10-27

Both parents branched from 10b7cb21af22 and each added its own columns; nothing
else needs to happen here, the merge just gives the schema a single head again.
"""

from collections.abc import Sequence

revision: str = "7d2e4f1a9c3b"
down_revision: str | Sequence[str] | None = ("a1b2c3d4e5f6", "a3f8d2c91b47")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Both parents already applied their columns; nothing to do."""


def downgrade() -> None:
    """Nothing to undo."""
