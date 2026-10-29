"""Database layer for audit persistence (experimental; needs the 'saas' extra)."""

from .._optional import require_saas

require_saas()

from .models import APIKey, Audit, AuditResult, Base, Organization, User  # noqa: E402
from .repositories import (  # noqa: E402
    APIKeyRepository,
    AuditRepository,
    OrganizationRepository,
    UsageRepository,
    UserRepository,
)

__all__ = [
    "Base",
    "User",
    "Organization",
    "Audit",
    "AuditResult",
    "APIKey",
    "UserRepository",
    "OrganizationRepository",
    "AuditRepository",
    "APIKeyRepository",
    "UsageRepository",
]
