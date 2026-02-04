"""Audit management endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...core.types import Query as QueryModel
from ..config import APISettings, get_settings
from ..routes.auth import oauth2_scheme, verify_token
from ..routes.users import get_current_user
from ..schemas import (
    AuditCancelRequest,
    AuditCreateRequest,
    AuditCreateResponse,
    AuditDetail,
    AuditListResponse,
    AuditStatus,
    AuditSummary,
)

router = APIRouter()


@router.post("", response_model=AuditCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_audit(
    audit_request: AuditCreateRequest,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> AuditCreateResponse:
    """
    Create a new search audit job.

    The audit runs asynchronously. Use the returned audit_id to check status.
    """
    payload = verify_token(token, settings)
    user_id = UUID(payload["sub"])

    user = await get_current_user(token, settings)

    from ...db.repositories import AuditRepository, UsageRepository  # type: ignore[import-untyped]
    from ...jobs.tasks import enqueue_audit  # type: ignore[import-untyped]
    from ..deps import get_db_session

    async for session in get_db_session():
        # Check usage limits
        usage_repo = UsageRepository(session)
        current_usage = await usage_repo.get_current_period(user_id)

        # Default limit - should be customized per plan
        if current_usage.audit_count >= 100:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Monthly audit limit exceeded",
            )

        # Create audit record
        audit_repo = AuditRepository(session)
        audit = await audit_repo.create(
            user_id=user_id,
            organization_id=user.organization_id,
            site_url=str(audit_request.site_url),
            queries=audit_request.queries,
            config_override=audit_request.config_override,
            headless=audit_request.headless,
            top_k=audit_request.top_k,
            webhook_url=str(audit_request.webhook_url) if audit_request.webhook_url else None,
        )

        # Enqueue job
        await enqueue_audit(
            audit_id=UUID(str(audit.id)),
            site_url=str(audit_request.site_url),
            queries=audit_request.queries,
            config_override=audit_request.config_override,
            headless=audit_request.headless,
            top_k=audit_request.top_k,
        )

        # Estimate duration (rough: 30s per query + 60s overhead)
        estimated_seconds = 60 + (len(audit_request.queries) * 30)

        return AuditCreateResponse(
            audit_id=UUID(str(audit.id)),
            status=AuditStatus.PENDING,
            message="Audit job created and queued for processing",
            estimated_duration_seconds=estimated_seconds,
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.get("", response_model=AuditListResponse)
async def list_audits(
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: AuditStatus | None = Query(default=None, alias="status"),
) -> AuditListResponse:
    """
    List audits for the current user.

    Supports pagination and filtering by status.
    """
    payload = verify_token(token, settings)
    user_id = UUID(payload["sub"])

    from ...db.repositories import AuditRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = AuditRepository(session)
        audits, total = await repo.list_by_user(
            user_id=user_id,
            page=page,
            page_size=page_size,
            status=status_filter,
        )

        pages = (total + page_size - 1) // page_size

        items = [
            AuditSummary(
                id=UUID(str(a.id)),
                site_url=a.site_url,
                status=AuditStatus(a.status),
                query_count=len(a.queries),
                completed_queries=a.completed_queries,
                average_score=a.average_score,
                created_at=a.created_at,
                started_at=a.started_at,
                completed_at=a.completed_at,
                error_message=a.error_message,
            )
            for a in audits
        ]

        return AuditListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.get("/{audit_id}", response_model=AuditDetail)
async def get_audit(
    audit_id: UUID,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> AuditDetail:
    """
    Get detailed information about an audit.

    Includes query results if the audit is completed.
    """
    payload = verify_token(token, settings)
    user_id = UUID(payload["sub"])

    from ...db.repositories import AuditRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = AuditRepository(session)
        audit = await repo.get_by_id(audit_id)

        if not audit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audit not found",
            )

        # Check ownership
        if audit.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this audit",
            )

        # Convert string queries to Query objects
        query_objects = [
            QueryModel(id=f"q{i}", text=q, lang="en") for i, q in enumerate(audit.queries)
        ]

        return AuditDetail(
            id=UUID(str(audit.id)),
            site_url=audit.site_url,
            status=AuditStatus(audit.status),
            query_count=len(audit.queries),
            completed_queries=audit.completed_queries,
            average_score=audit.average_score,
            created_at=audit.created_at,
            started_at=audit.started_at,
            completed_at=audit.completed_at,
            error_message=audit.error_message,
            queries=query_objects,
            config=audit.config_override or {},
            results=None,  # TODO: Convert results when available
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.post("/{audit_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_audit(
    audit_id: UUID,
    cancel_request: AuditCancelRequest,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> dict[str, str]:
    """
    Cancel a running audit.

    Only audits with status PENDING or RUNNING can be cancelled.
    """
    payload = verify_token(token, settings)
    user_id = UUID(payload["sub"])

    from ...db.repositories import AuditRepository
    from ...jobs.tasks import cancel_audit_job
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = AuditRepository(session)
        audit = await repo.get_by_id(audit_id)

        if not audit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audit not found",
            )

        if audit.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to cancel this audit",
            )

        if audit.status not in ["pending", "running"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel audit with status: {audit.status}",
            )

        # Cancel the job
        await cancel_audit_job(audit_id)

        # Update status
        await repo.update_status(
            audit_id,
            status="cancelled",
            error_message=cancel_request.reason or "Cancelled by user",
        )

        return {"message": "Audit cancelled successfully"}

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.delete("/{audit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_audit(
    audit_id: UUID,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> None:
    """
    Delete an audit and its results.

    This action is irreversible.
    """
    payload = verify_token(token, settings)
    user_id = UUID(payload["sub"])

    from ...db.repositories import AuditRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = AuditRepository(session)
        audit = await repo.get_by_id(audit_id)

        if not audit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audit not found",
            )

        if audit.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this audit",
            )

        await repo.delete(audit_id)
        return

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.get("/{audit_id}/report")
async def get_audit_report(
    audit_id: UUID,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
    format: str = Query(default="html", pattern="^(html|md|json)$"),
) -> dict[str, str]:
    """
    Get the audit report in the specified format.

    Only available for completed audits.
    """
    payload = verify_token(token, settings)
    user_id = UUID(payload["sub"])

    from ...db.repositories import AuditRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = AuditRepository(session)
        audit = await repo.get_by_id(audit_id)

        if not audit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audit not found",
            )

        if audit.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this audit",
            )

        if audit.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Report is only available for completed audits",
            )

        report = await repo.get_report(audit_id, format)

        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found",
            )

        return {
            "format": format,
            "content": report.content,
            "generated_at": report.generated_at.isoformat(),
        }

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )
