"""User management endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import APISettings, get_settings
from ..routes.auth import oauth2_scheme, verify_token
from ..schemas import (
    OrganizationCreate,
    OrganizationResponse,
    UsageLimits,
    UsageSummary,
    UserResponse,
)

router = APIRouter()


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> "User":  # type: ignore[name-defined]  # noqa: F821
    """Get the current authenticated user."""

    payload = verify_token(token, settings)
    user_id = UUID(payload["sub"])

    from ...db.repositories import UserRepository  # type: ignore[import-untyped]
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = UserRepository(session)
        user = await repo.get_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled",
            )

        return user

    # Should never reach here - get_db_session always yields
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> UserResponse:
    """
    Get the current user's profile.
    """
    user = await get_current_user(token, settings)

    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        is_active=user.is_active,
        is_admin=user.is_admin,
        created_at=user.created_at,
        organization_id=user.organization_id,
    )


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    updates: dict,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> UserResponse:
    """
    Update the current user's profile.

    Allowed fields: name
    """
    user = await get_current_user(token, settings)

    from ...db.repositories import UserRepository
    from ..deps import get_db_session

    allowed_fields = {"name"}
    filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not filtered_updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid fields to update",
        )

    async for session in get_db_session():
        repo = UserRepository(session)
        updated_user = await repo.update(user.id, **filtered_updates)
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return UserResponse(
            id=UUID(str(updated_user.id)),
            email=updated_user.email,
            name=updated_user.name,
            is_active=updated_user.is_active,
            is_admin=updated_user.is_admin,
            created_at=updated_user.created_at,
            organization_id=(
                UUID(str(updated_user.organization_id)) if updated_user.organization_id else None
            ),
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.get("/me/usage", response_model=UsageSummary)
async def get_usage(
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> UsageSummary:
    """
    Get usage statistics for the current user.
    """
    user = await get_current_user(token, settings)

    from ...db.repositories import UsageRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = UsageRepository(session)
        current_period = await repo.get_current_period(user.id)
        all_time = await repo.get_all_time(user.id)

        # Default limits (can be customized per plan)
        limits = UsageLimits(
            audits_per_month=100,
            queries_per_audit=100,
            concurrent_audits=3,
        )

        return UsageSummary(
            current_period=current_period,
            all_time=all_time,
            limits=limits,
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


# Organization endpoints


@router.post(
    "/organizations", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED
)
async def create_organization(
    org_data: OrganizationCreate,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> OrganizationResponse:
    """
    Create a new organization.

    The creating user becomes the owner.
    """
    user = await get_current_user(token, settings)

    from ...db.repositories import OrganizationRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = OrganizationRepository(session)
        org = await repo.create(name=org_data.name, owner_id=user.id)

        return OrganizationResponse(
            id=UUID(str(org.id)),
            name=org.name,
            created_at=org.created_at,
            member_count=1,
            audit_count=0,
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.get("/organizations/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: UUID,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> OrganizationResponse:
    """
    Get organization details.

    User must be a member of the organization.
    """
    user = await get_current_user(token, settings)

    from ...db.repositories import OrganizationRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = OrganizationRepository(session)
        org = await repo.get_by_id(org_id)

        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )

        # Check membership
        is_member = await repo.is_member(org_id, user.id)
        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this organization",
            )

        member_count = await repo.get_member_count(org_id)
        audit_count = await repo.get_audit_count(org_id)

        return OrganizationResponse(
            id=UUID(str(org.id)),
            name=org.name,
            created_at=org.created_at,
            member_count=member_count,
            audit_count=audit_count,
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )
