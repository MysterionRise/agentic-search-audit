"""Authentication endpoints."""

from datetime import datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from ..config import APISettings, get_settings
from ..schemas import (
    APIKeyCreate,
    APIKeyListItem,
    APIKeyResponse,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def create_access_token(
    user_id: UUID,
    settings: APISettings,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token."""
    import jwt

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours)

    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
    }

    token: str = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token


def verify_token(token: str, settings: APISettings) -> dict[str, Any]:
    """Verify and decode a JWT token."""
    import jwt

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    import bcrypt

    hashed: str = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    return hashed


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    import bcrypt

    result: bool = bcrypt.checkpw(password.encode(), hashed.encode())
    return result


def generate_api_key() -> tuple[str, str]:
    """Generate an API key and its prefix."""
    import secrets

    key = secrets.token_urlsafe(32)
    prefix = key[:8]
    return key, prefix


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    settings: Annotated[APISettings, Depends(get_settings)],
) -> UserResponse:
    """
    Register a new user account.

    Creates a new user with the provided email and password.
    """
    from ...db.repositories import UserRepository  # type: ignore[import-untyped]
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = UserRepository(session)

        # Check if user exists
        existing = await repo.get_by_email(user_data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists",
            )

        # Create user
        password_hash = hash_password(user_data.password)
        user = await repo.create(
            email=user_data.email,
            name=user_data.name,
            password_hash=password_hash,
        )

        return UserResponse(
            id=UUID(str(user.id)),
            email=user.email,
            name=user.name,
            is_active=user.is_active,
            is_admin=user.is_admin,
            created_at=user.created_at,
            organization_id=UUID(str(user.organization_id)) if user.organization_id else None,
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.post("/token", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> TokenResponse:
    """
    OAuth2 token endpoint.

    Exchange username/password for an access token.
    """
    from ...db.repositories import UserRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = UserRepository(session)
        user = await repo.get_by_email(form_data.username)

        if not user or not verify_password(form_data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled",
            )

        access_token = create_access_token(UUID(str(user.id)), settings)

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.jwt_expiration_hours * 3600,
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.post("/login", response_model=TokenResponse)
async def login_json(
    credentials: UserLogin,
    settings: Annotated[APISettings, Depends(get_settings)],
) -> TokenResponse:
    """
    JSON login endpoint.

    Alternative to OAuth2 form-based login.
    """
    from ...db.repositories import UserRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = UserRepository(session)
        user = await repo.get_by_email(credentials.email)

        if not user or not verify_password(credentials.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled",
            )

        access_token = create_access_token(UUID(str(user.id)), settings)

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.jwt_expiration_hours * 3600,
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.post("/api-keys", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    key_data: APIKeyCreate,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> APIKeyResponse:
    """
    Create a new API key for the authenticated user.

    The full key is only returned once upon creation.
    """
    payload = verify_token(token, settings)
    user_id = UUID(payload["sub"])

    from ...db.repositories import APIKeyRepository
    from ..deps import get_db_session

    key, prefix = generate_api_key()
    key_hash = hash_password(key)

    async for session in get_db_session():
        repo = APIKeyRepository(session)
        api_key = await repo.create(
            user_id=user_id,
            name=key_data.name,
            key_hash=key_hash,
            prefix=prefix,
            expires_at=key_data.expires_at,
        )

        return APIKeyResponse(
            id=UUID(str(api_key.id)),
            name=api_key.name,
            key=key,  # Only returned once
            prefix=prefix,
            created_at=api_key.created_at,
            expires_at=api_key.expires_at,
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.get("/api-keys", response_model=list[APIKeyListItem])
async def list_api_keys(
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> list[APIKeyListItem]:
    """
    List all API keys for the authenticated user.
    """
    payload = verify_token(token, settings)
    user_id = UUID(payload["sub"])

    from ...db.repositories import APIKeyRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = APIKeyRepository(session)
        keys = await repo.list_by_user(user_id)

        return [
            APIKeyListItem(
                id=UUID(str(k.id)),
                name=k.name,
                prefix=k.prefix,
                created_at=k.created_at,
                expires_at=k.expires_at,
                last_used_at=k.last_used_at,
            )
            for k in keys
        ]

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database session unavailable",
    )


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: UUID,
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: Annotated[APISettings, Depends(get_settings)],
) -> None:
    """
    Delete an API key.
    """
    payload = verify_token(token, settings)
    user_id = UUID(payload["sub"])

    from ...db.repositories import APIKeyRepository
    from ..deps import get_db_session

    async for session in get_db_session():
        repo = APIKeyRepository(session)
        deleted = await repo.delete(key_id, user_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found",
            )
