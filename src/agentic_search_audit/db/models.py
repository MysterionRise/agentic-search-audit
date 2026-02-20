"""SQLAlchemy database models."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class User(Base):
    """User account model."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plan_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    organization_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # GDPR consent columns
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    consent_analytics: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    consent_third_party: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    consent_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # GDPR deletion columns
    deletion_scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deletion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    organization: Mapped["Organization | None"] = relationship(
        "Organization", back_populates="members"
    )
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey", back_populates="user", cascade="all, delete-orphan"
    )
    audits: Mapped[list["Audit"]] = relationship(
        "Audit", back_populates="user", cascade="all, delete-orphan"
    )


class Organization(Base):
    """Organization for multi-tenant support."""

    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    members: Mapped[list["User"]] = relationship("User", back_populates="organization")
    audits: Mapped[list["Audit"]] = relationship("Audit", back_populates="organization")


class APIKey(Base):
    """API key for authentication."""

    __tablename__ = "api_keys"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    prefix: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="api_keys")


class Audit(Base):
    """Audit job model."""

    __tablename__ = "audits"
    __table_args__ = (
        Index("ix_audits_user_created", "user_id", "created_at"),
        Index("ix_audits_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )
    site_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    queries: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    config_override: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    headless: Mapped[bool] = mapped_column(Boolean, default=True)
    top_k: Mapped[int] = mapped_column(Integer, default=10)
    webhook_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    completed_queries: Mapped[int] = mapped_column(Integer, default=0)
    average_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="audits")
    organization: Mapped["Organization | None"] = relationship(
        "Organization", back_populates="audits"
    )
    results: Mapped[list["AuditResult"]] = relationship(
        "AuditResult", back_populates="audit", cascade="all, delete-orphan"
    )
    reports: Mapped[list["AuditReport"]] = relationship(
        "AuditReport", back_populates="audit", cascade="all, delete-orphan"
    )


class AuditResult(Base):
    """Individual query result within an audit."""

    __tablename__ = "audit_results"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    audit_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audits.id"), nullable=False
    )
    query_text: Mapped[str] = mapped_column(String(1000), nullable=False)
    query_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    score: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    screenshot_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    html_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    audit: Mapped["Audit"] = relationship("Audit", back_populates="results")


class AuditReport(Base):
    """Generated report for an audit."""

    __tablename__ = "audit_reports"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    audit_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("audits.id"), nullable=False
    )
    format: Mapped[str] = mapped_column(String(10), nullable=False)  # html, md, json
    content: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    audit: Mapped["Audit"] = relationship("Audit", back_populates="reports")


class UsageRecord(Base):
    """Usage tracking for billing."""

    __tablename__ = "usage_records"
    __table_args__ = (Index("ix_usage_user_period", "user_id", "period_start"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    audit_count: Mapped[int] = mapped_column(Integer, default=0)
    query_count: Mapped[int] = mapped_column(Integer, default=0)
    llm_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
