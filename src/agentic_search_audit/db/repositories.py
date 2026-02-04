"""Repository classes for database operations."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.schemas import UsageRecord as UsageRecordSchema
from .models import APIKey, Audit, AuditReport, AuditResult, Organization, UsageRecord, User


class UserRepository:
    """Repository for user operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        email: str,
        password_hash: str,
        name: str | None = None,
    ) -> User:
        """Create a new user."""
        user = User(
            email=email,
            password_hash=password_hash,
            name=name,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Get user by ID."""
        result = await self.session.execute(select(User).where(User.id == user_id))
        row: User | None = result.scalar_one_or_none()
        return row

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email."""
        result = await self.session.execute(select(User).where(User.email == email))
        row: User | None = result.scalar_one_or_none()
        return row

    async def update(self, user_id: UUID, **kwargs: Any) -> User | None:
        """Update user attributes."""
        await self.session.execute(update(User).where(User.id == user_id).values(**kwargs))
        await self.session.flush()
        return await self.get_by_id(user_id)


class OrganizationRepository:
    """Repository for organization operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, name: str, owner_id: UUID) -> Organization:
        """Create a new organization."""
        org = Organization(name=name, owner_id=owner_id)
        self.session.add(org)
        await self.session.flush()

        # Update owner's organization_id
        await self.session.execute(
            update(User).where(User.id == owner_id).values(organization_id=org.id)
        )

        return org

    async def get_by_id(self, org_id: UUID) -> Organization | None:
        """Get organization by ID."""
        result = await self.session.execute(select(Organization).where(Organization.id == org_id))
        row: Organization | None = result.scalar_one_or_none()
        return row

    async def is_member(self, org_id: UUID, user_id: UUID) -> bool:
        """Check if user is member of organization."""
        result = await self.session.execute(
            select(User).where(
                User.id == user_id,
                User.organization_id == org_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_member_count(self, org_id: UUID) -> int:
        """Get number of members in organization."""
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.organization_id == org_id)
        )
        return result.scalar() or 0

    async def get_audit_count(self, org_id: UUID) -> int:
        """Get number of audits in organization."""
        result = await self.session.execute(
            select(func.count()).select_from(Audit).where(Audit.organization_id == org_id)
        )
        return result.scalar() or 0


class APIKeyRepository:
    """Repository for API key operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: UUID,
        name: str,
        key_hash: str,
        prefix: str,
        expires_at: datetime | None = None,
    ) -> APIKey:
        """Create a new API key."""
        api_key = APIKey(
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            prefix=prefix,
            expires_at=expires_at,
        )
        self.session.add(api_key)
        await self.session.flush()
        return api_key

    async def list_by_user(self, user_id: UUID) -> list[APIKey]:
        """List all API keys for a user."""
        result = await self.session.execute(
            select(APIKey).where(APIKey.user_id == user_id).order_by(APIKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_prefix(self, prefix: str) -> APIKey | None:
        """Get API key by prefix."""
        result = await self.session.execute(select(APIKey).where(APIKey.prefix == prefix))
        row: APIKey | None = result.scalar_one_or_none()
        return row

    async def update_last_used(self, key_id: UUID) -> None:
        """Update last used timestamp."""
        await self.session.execute(
            update(APIKey).where(APIKey.id == key_id).values(last_used_at=datetime.utcnow())
        )

    async def delete(self, key_id: UUID, user_id: UUID) -> bool:
        """Delete an API key."""
        result = await self.session.execute(
            delete(APIKey).where(
                APIKey.id == key_id,
                APIKey.user_id == user_id,
            )
        )
        rowcount = getattr(result, "rowcount", 0)
        return bool(rowcount and rowcount > 0)


class AuditRepository:
    """Repository for audit operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: UUID,
        site_url: str,
        queries: list[str],
        organization_id: UUID | None = None,
        config_override: dict[str, Any] | None = None,
        headless: bool = True,
        top_k: int = 10,
        webhook_url: str | None = None,
    ) -> Audit:
        """Create a new audit."""
        audit = Audit(
            user_id=user_id,
            organization_id=organization_id,
            site_url=site_url,
            queries=queries,
            config_override=config_override,
            headless=headless,
            top_k=top_k,
            webhook_url=webhook_url,
        )
        self.session.add(audit)
        await self.session.flush()
        return audit

    async def get_by_id(self, audit_id: UUID) -> Audit | None:
        """Get audit by ID."""
        result = await self.session.execute(select(Audit).where(Audit.id == audit_id))
        row: Audit | None = result.scalar_one_or_none()
        return row

    async def list_by_user(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> tuple[list[Audit], int]:
        """List audits for a user with pagination."""
        query = select(Audit).where(Audit.user_id == user_id)

        if status:
            query = query.where(Audit.status == status)

        # Get total count
        count_result = await self.session.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar() or 0

        # Get paginated results
        query = query.order_by(Audit.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        audits = list(result.scalars().all())

        return audits, total

    async def update_status(
        self,
        audit_id: UUID,
        status: str,
        error_message: str | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        """Update audit status."""
        values: dict[str, Any] = {"status": status}
        if error_message is not None:
            values["error_message"] = error_message
        if completed_at is not None:
            values["completed_at"] = completed_at
        if status == "running":
            values["started_at"] = datetime.utcnow()

        await self.session.execute(update(Audit).where(Audit.id == audit_id).values(**values))

    async def update_progress(
        self,
        audit_id: UUID,
        completed_queries: int,
        average_score: float | None = None,
    ) -> None:
        """Update audit progress."""
        values: dict[str, Any] = {"completed_queries": completed_queries}
        if average_score is not None:
            values["average_score"] = average_score

        await self.session.execute(update(Audit).where(Audit.id == audit_id).values(**values))

    async def add_result(
        self,
        audit_id: UUID,
        query_text: str,
        query_data: dict[str, Any],
        items: list[dict[str, Any]],
        score: dict[str, Any],
        screenshot_path: str | None = None,
        html_path: str | None = None,
    ) -> AuditResult:
        """Add a result to an audit."""
        result = AuditResult(
            audit_id=audit_id,
            query_text=query_text,
            query_data=query_data,
            items=items,
            score=score,
            screenshot_path=screenshot_path,
            html_path=html_path,
        )
        self.session.add(result)
        await self.session.flush()
        return result

    async def get_results(self, audit_id: UUID) -> list[AuditResult]:
        """Get all results for an audit."""
        result = await self.session.execute(
            select(AuditResult)
            .where(AuditResult.audit_id == audit_id)
            .order_by(AuditResult.created_at)
        )
        return list(result.scalars().all())

    async def add_report(
        self,
        audit_id: UUID,
        format: str,
        content: str,
    ) -> AuditReport:
        """Add a report to an audit."""
        report = AuditReport(
            audit_id=audit_id,
            format=format,
            content=content,
        )
        self.session.add(report)
        await self.session.flush()
        return report

    async def get_report(self, audit_id: UUID, format: str) -> AuditReport | None:
        """Get a report for an audit."""
        result = await self.session.execute(
            select(AuditReport).where(
                AuditReport.audit_id == audit_id,
                AuditReport.format == format,
            )
        )
        row: AuditReport | None = result.scalar_one_or_none()
        return row

    async def delete(self, audit_id: UUID) -> None:
        """Delete an audit and all related data."""
        await self.session.execute(delete(Audit).where(Audit.id == audit_id))


class UsageRepository:
    """Repository for usage tracking."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_current_period(self, user_id: UUID) -> UsageRecordSchema:
        """Get current billing period usage."""
        # Get start of current month
        now = datetime.utcnow()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)

        # Get or create usage record
        result = await self.session.execute(
            select(UsageRecord).where(
                UsageRecord.user_id == user_id,
                UsageRecord.period_start == period_start,
            )
        )
        record = result.scalar_one_or_none()

        if record:
            return UsageRecordSchema(
                period_start=record.period_start,
                period_end=record.period_end,
                audit_count=record.audit_count,
                query_count=record.query_count,
                llm_tokens_used=record.llm_tokens_used,
                estimated_cost_usd=record.llm_tokens_used * 0.00001,  # Rough estimate
            )

        # Return empty record if none exists
        return UsageRecordSchema(
            period_start=period_start,
            period_end=period_end,
            audit_count=0,
            query_count=0,
            llm_tokens_used=0,
            estimated_cost_usd=0.0,
        )

    async def get_all_time(self, user_id: UUID) -> UsageRecordSchema:
        """Get all-time usage."""
        result = await self.session.execute(
            select(
                func.sum(UsageRecord.audit_count),
                func.sum(UsageRecord.query_count),
                func.sum(UsageRecord.llm_tokens_used),
                func.min(UsageRecord.period_start),
            ).where(UsageRecord.user_id == user_id)
        )
        row = result.one()

        return UsageRecordSchema(
            period_start=row[3] or datetime.utcnow(),
            period_end=datetime.utcnow(),
            audit_count=row[0] or 0,
            query_count=row[1] or 0,
            llm_tokens_used=row[2] or 0,
            estimated_cost_usd=(row[2] or 0) * 0.00001,
        )

    async def increment_usage(
        self,
        user_id: UUID,
        audit_count: int = 0,
        query_count: int = 0,
        llm_tokens: int = 0,
    ) -> None:
        """Increment usage counters for current period."""
        now = datetime.utcnow()
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = (period_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)

        # Try to update existing record
        result = await self.session.execute(
            update(UsageRecord)
            .where(
                UsageRecord.user_id == user_id,
                UsageRecord.period_start == period_start,
            )
            .values(
                audit_count=UsageRecord.audit_count + audit_count,
                query_count=UsageRecord.query_count + query_count,
                llm_tokens_used=UsageRecord.llm_tokens_used + llm_tokens,
            )
        )

        # Create new record if none exists
        rowcount = getattr(result, "rowcount", 0)
        if not rowcount or rowcount == 0:
            record = UsageRecord(
                user_id=user_id,
                period_start=period_start,
                period_end=period_end,
                audit_count=audit_count,
                query_count=query_count,
                llm_tokens_used=llm_tokens,
            )
            self.session.add(record)
