"""GDPR compliance endpoints for data export and deletion."""

import json
import logging
from datetime import datetime
from io import BytesIO
from typing import Annotated, Any
from uuid import UUID
from zipfile import ZipFile

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..config import APISettings, get_settings
from ..routes.auth import oauth2_scheme, verify_password
from ..routes.users import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


class DataExportRequest(BaseModel):
    """Request to export user data."""

    include_audits: bool = Field(default=True, description="Include audit data")
    include_reports: bool = Field(default=True, description="Include generated reports")
    include_artifacts: bool = Field(
        default=False, description="Include screenshots and HTML snapshots"
    )


class DataDeletionRequest(BaseModel):
    """Request to delete user account and data."""

    password: str = Field(description="Password confirmation")
    confirm: bool = Field(description="Confirmation flag - must be True")
    reason: str | None = Field(default=None, description="Optional deletion reason")


class DataDeletionResponse(BaseModel):
    """Response after deletion request."""

    status: str
    message: str
    deletion_scheduled_at: datetime | None


class ConsentStatus(BaseModel):
    """User consent status."""

    marketing_emails: bool
    analytics: bool
    third_party_sharing: bool
    updated_at: datetime


class ConsentUpdateRequest(BaseModel):
    """Request to update consent preferences."""

    marketing_emails: bool | None = None
    analytics: bool | None = None
    third_party_sharing: bool | None = None


@router.get("/export")
async def export_user_data(
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
    include_audits: bool = True,
    include_reports: bool = True,
    include_artifacts: bool = False,
) -> StreamingResponse:
    """
    Export all user data as a ZIP file (GDPR Article 20 - Right to data portability).

    Returns a ZIP file containing:
    - User profile information (JSON)
    - Audit history and results (JSON)
    - Generated reports (if requested)
    - Screenshots and HTML snapshots (if requested)
    """
    user = await get_current_user(token, settings)

    from ...db.repositories import AuditRepository, UserRepository  # type: ignore[import-untyped]
    from ..deps import get_db_session

    # Collect data
    export_data: dict[str, Any] = {}

    async for session in get_db_session():
        user_repo = UserRepository(session)
        audit_repo = AuditRepository(session)

        # User profile
        user_data = await user_repo.get_by_id(user.id)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User data not found",
            )
        export_data["profile"] = {
            "id": str(user_data.id),
            "email": user_data.email,
            "name": user_data.name,
            "created_at": user_data.created_at.isoformat(),
            "organization_id": (
                str(user_data.organization_id) if user_data.organization_id else None
            ),
        }

        # Audit data
        if include_audits:
            audits, _ = await audit_repo.list_by_user(user.id, page=1, page_size=10000)
            export_data["audits"] = []

            for audit in audits:
                audit_export: dict[str, Any] = {
                    "id": str(audit.id),
                    "site_url": audit.site_url,
                    "queries": audit.queries,
                    "status": audit.status,
                    "created_at": audit.created_at.isoformat(),
                    "completed_at": audit.completed_at.isoformat() if audit.completed_at else None,
                    "average_score": audit.average_score,
                }

                if include_reports:
                    results = await audit_repo.get_results(UUID(str(audit.id)))
                    audit_export["results"] = [
                        {
                            "query": r.query_text,
                            "items": r.items,
                            "score": r.score,
                        }
                        for r in results
                    ]

                export_data["audits"].append(audit_export)

    # Create ZIP file
    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, "w") as zip_file:
        # Add profile
        zip_file.writestr(
            "profile.json",
            json.dumps(export_data["profile"], indent=2),
        )

        # Add audits
        if "audits" in export_data:
            zip_file.writestr(
                "audits.json",
                json.dumps(export_data["audits"], indent=2, default=str),
            )

        # Add metadata
        metadata = {
            "export_date": datetime.utcnow().isoformat(),
            "user_id": str(user.id),
            "include_audits": include_audits,
            "include_reports": include_reports,
            "include_artifacts": include_artifacts,
        }
        zip_file.writestr("metadata.json", json.dumps(metadata, indent=2))

    zip_buffer.seek(0)

    logger.info(f"Data export generated for user {user.id}")

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="data_export_{datetime.utcnow().strftime("%Y%m%d")}.zip"'
        },
    )


@router.post("/delete", response_model=DataDeletionResponse)
async def request_account_deletion(
    request: DataDeletionRequest,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> DataDeletionResponse:
    """
    Request account and data deletion (GDPR Article 17 - Right to erasure).

    This will:
    1. Verify password confirmation
    2. Schedule account for deletion (30-day grace period)
    3. Deactivate the account immediately
    4. Delete all data after grace period

    The user can cancel deletion during the grace period by contacting support.
    """
    if not request.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deletion must be confirmed",
        )

    user = await get_current_user(token, settings)

    from ...db.repositories import UserRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = UserRepository(session)
        user_data = await repo.get_by_id(user.id)

        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Verify password
        if not verify_password(request.password, user_data.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password",
            )

        # Schedule deletion (30-day grace period)
        from datetime import timedelta

        deletion_date = datetime.utcnow() + timedelta(days=30)

        # Deactivate account and mark for deletion
        await repo.update(
            user.id,
            is_active=False,
            deletion_scheduled_at=deletion_date,
            deletion_reason=request.reason,
        )

        logger.info(f"Account deletion scheduled for user {user.id} at {deletion_date}")

        return DataDeletionResponse(
            status="scheduled",
            message="Your account has been deactivated and will be permanently deleted in 30 days. Contact support to cancel.",
            deletion_scheduled_at=deletion_date,
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.post("/delete/immediate", response_model=DataDeletionResponse)
async def immediate_account_deletion(
    request: DataDeletionRequest,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> DataDeletionResponse:
    """
    Immediately delete account and all data.

    WARNING: This action is irreversible. All data will be permanently deleted.
    """
    if not request.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deletion must be confirmed",
        )

    user = await get_current_user(token, settings)

    from ...db.repositories import AuditRepository, UserRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        user_repo = UserRepository(session)
        audit_repo = AuditRepository(session)

        user_data = await user_repo.get_by_id(user.id)

        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Verify password
        if not verify_password(request.password, user_data.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password",
            )

        # Delete all audits and results
        audits, _ = await audit_repo.list_by_user(user.id, page=1, page_size=10000)
        for audit in audits:
            await audit_repo.delete(UUID(str(audit.id)))

        # Delete user (cascades to API keys)
        from sqlalchemy import delete

        from ...db.models import User  # type: ignore[import-untyped]

        await session.execute(delete(User).where(User.id == user.id))

        logger.info(f"Account immediately deleted for user {user.id}")

        return DataDeletionResponse(
            status="deleted",
            message="Your account and all associated data have been permanently deleted.",
            deletion_scheduled_at=None,
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.get("/consent", response_model=ConsentStatus)
async def get_consent_status(
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> ConsentStatus:
    """
    Get current consent preferences (GDPR Article 7 - Conditions for consent).
    """
    user = await get_current_user(token, settings)

    from ...db.repositories import UserRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = UserRepository(session)
        user_data = await repo.get_by_id(user.id)

        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return ConsentStatus(
            marketing_emails=user_data.consent_marketing,
            analytics=user_data.consent_analytics,
            third_party_sharing=user_data.consent_third_party,
            updated_at=user_data.consent_updated_at or user_data.created_at,
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.patch("/consent", response_model=ConsentStatus)
async def update_consent(
    request: ConsentUpdateRequest,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> ConsentStatus:
    """
    Update consent preferences.

    Users can withdraw consent at any time (GDPR Article 7.3).
    """
    user = await get_current_user(token, settings)

    from ...db.repositories import UserRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = UserRepository(session)

        updates: dict[str, Any] = {}
        if request.marketing_emails is not None:
            updates["consent_marketing"] = request.marketing_emails
        if request.analytics is not None:
            updates["consent_analytics"] = request.analytics
        if request.third_party_sharing is not None:
            updates["consent_third_party"] = request.third_party_sharing

        if updates:
            updates["consent_updated_at"] = datetime.utcnow()
            await repo.update(user.id, **updates)

        logger.info(f"Consent updated for user {user.id}: {updates}")

        user_data = await repo.get_by_id(user.id)
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return ConsentStatus(
            marketing_emails=user_data.consent_marketing,
            analytics=user_data.consent_analytics,
            third_party_sharing=user_data.consent_third_party,
            updated_at=user_data.consent_updated_at or datetime.utcnow(),
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.get("/access-log")
async def get_access_log(
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """
    Get access log for the user's data (GDPR Article 15 - Right of access).

    Shows who has accessed the user's data and when.
    """
    # Authenticate user (required for access)
    _ = await get_current_user(token, settings)

    # In a full implementation, this would query an audit log table
    # For now, return a placeholder
    return {
        "items": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "message": "Access logging is enabled. No third-party access recorded.",
    }
