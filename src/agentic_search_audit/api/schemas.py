"""API request/response schemas."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any
from urllib.parse import urlparse
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, HttpUrl

from ..core.types import JudgeScore, Query, ResultItem

# Blocked hostnames for webhook URLs (SSRF prevention)
_WEBHOOK_BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",  # nosec B104 - not binding, blocking this address
    "::1",
    "[::1]",
}

# Blocked IP prefixes (internal networks)
_WEBHOOK_BLOCKED_PREFIXES = (
    "10.",
    "192.168.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "169.254.",
)


def validate_webhook_url(url: HttpUrl) -> HttpUrl:
    """Validate webhook URL to prevent SSRF attacks."""
    parsed = urlparse(str(url))
    hostname = (parsed.hostname or "").lower()

    if hostname in _WEBHOOK_BLOCKED_HOSTS:
        raise ValueError("Webhook URL cannot point to localhost or loopback address")

    if hostname.startswith(_WEBHOOK_BLOCKED_PREFIXES):
        raise ValueError("Webhook URL cannot point to internal network addresses")

    return url


# Type alias for validated webhook URL
SafeWebhookUrl = Annotated[HttpUrl, AfterValidator(validate_webhook_url)]


class AuditStatus(str, Enum):
    """Audit job status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Request schemas


class AuditCreateRequest(BaseModel):
    """Request to create a new audit."""

    site_url: HttpUrl = Field(description="URL of the site to audit")
    queries: list[str] = Field(
        min_length=1,
        max_length=100,
        description="List of search queries to evaluate",
    )
    config_override: dict[str, Any] | None = Field(
        default=None,
        description="Optional configuration overrides",
    )
    headless: bool = Field(default=True, description="Run browser in headless mode")
    top_k: int = Field(default=10, ge=1, le=50, description="Number of results to extract")
    webhook_url: SafeWebhookUrl | None = Field(
        default=None,
        description="Webhook URL for completion notification. Cannot point to localhost or internal networks.",
    )


class AuditCancelRequest(BaseModel):
    """Request to cancel an audit."""

    reason: str | None = Field(default=None, description="Cancellation reason")


# Response schemas


class AuditSummary(BaseModel):
    """Summary of an audit run."""

    id: UUID
    site_url: str
    status: AuditStatus
    query_count: int
    completed_queries: int
    average_score: float | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None


class AuditDetail(AuditSummary):
    """Detailed audit information."""

    queries: list[Query]
    config: dict[str, Any]
    results: list["AuditResultItem"] | None


class AuditResultItem(BaseModel):
    """Single query result in an audit."""

    query: Query
    items: list[ResultItem]
    score: JudgeScore
    artifacts: "ArtifactLinks"


class ArtifactLinks(BaseModel):
    """Links to audit artifacts."""

    screenshot_url: str | None
    html_snapshot_url: str | None


class AuditCreateResponse(BaseModel):
    """Response after creating an audit."""

    audit_id: UUID
    status: AuditStatus
    message: str
    estimated_duration_seconds: int | None


class AuditListResponse(BaseModel):
    """Paginated list of audits."""

    items: list[AuditSummary]
    total: int
    page: int
    page_size: int
    pages: int


# User schemas


class UserBase(BaseModel):
    """Base user model."""

    email: str = Field(description="User email address")
    name: str | None = Field(default=None, description="Display name")


class UserCreate(UserBase):
    """User creation request."""

    password: str = Field(min_length=8, description="User password")


class UserResponse(UserBase):
    """User response model."""

    id: UUID
    is_active: bool
    is_admin: bool
    created_at: datetime
    organization_id: UUID | None


class UserLogin(BaseModel):
    """User login request."""

    email: str
    password: str


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class APIKeyCreate(BaseModel):
    """API key creation request."""

    name: str = Field(min_length=1, max_length=100, description="Key name/description")
    expires_at: datetime | None = Field(default=None, description="Expiration date")


class APIKeyResponse(BaseModel):
    """API key response (only returned once on creation)."""

    id: UUID
    name: str
    key: str  # Only returned on creation
    prefix: str
    created_at: datetime
    expires_at: datetime | None


class APIKeyListItem(BaseModel):
    """API key in list (without full key)."""

    id: UUID
    name: str
    prefix: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None


# Organization schemas


class OrganizationBase(BaseModel):
    """Base organization model."""

    name: str = Field(min_length=1, max_length=200)


class OrganizationCreate(OrganizationBase):
    """Organization creation request."""

    pass


class OrganizationResponse(OrganizationBase):
    """Organization response model."""

    id: UUID
    created_at: datetime
    member_count: int
    audit_count: int


# Usage/Billing schemas


class UsageRecord(BaseModel):
    """Usage record for billing."""

    period_start: datetime
    period_end: datetime
    audit_count: int
    query_count: int
    llm_tokens_used: int
    estimated_cost_usd: float


class UsageSummary(BaseModel):
    """Usage summary response."""

    current_period: UsageRecord
    all_time: UsageRecord
    limits: "UsageLimits"


class UsageLimits(BaseModel):
    """Usage limits for the plan."""

    audits_per_month: int | None
    queries_per_audit: int
    concurrent_audits: int


# Health check schemas


class HealthStatus(BaseModel):
    """Health check status."""

    status: str = Field(description="Overall status: healthy, degraded, unhealthy")
    version: str
    timestamp: datetime
    checks: dict[str, "ComponentHealth"]


class ComponentHealth(BaseModel):
    """Individual component health."""

    status: str
    latency_ms: float | None
    message: str | None


# Enable forward references
AuditDetail.model_rebuild()
AuditResultItem.model_rebuild()
UsageSummary.model_rebuild()
HealthStatus.model_rebuild()
