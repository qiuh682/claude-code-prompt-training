"""Authentication routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import get_current_user
from apps.api.auth.models import User
from apps.api.auth.schemas import (
    LoginResponse,
    LogoutRequest,
    MessageResponse,
    TokenRefresh,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)
from apps.api.auth.service import (
    InvalidCredentialsError,
    InvalidTokenError,
    UserExistsError,
    UserInactiveError,
    authenticate_user,
    create_tokens,
    create_user,
    get_token_expiry_seconds,
    refresh_tokens,
    revoke_all_user_tokens,
    revoke_refresh_token,
)
from apps.api.db import get_db

router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_client_info(request: Request) -> tuple[str | None, str | None]:
    """Extract user agent and IP from request."""
    user_agent = request.headers.get("user-agent")
    # Handle proxy headers
    ip_address = request.headers.get("x-forwarded-for")
    if ip_address:
        ip_address = ip_address.split(",")[0].strip()
    else:
        ip_address = request.client.host if request.client else None
    return user_agent, ip_address


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: UserRegister,
    db: Session = Depends(get_db),
) -> User:
    """Register a new user account."""
    try:
        user = create_user(db, data)
        return user
    except UserExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from None


@router.post("/login", response_model=LoginResponse)
def login(
    data: UserLogin,
    request: Request,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """Login with email and password."""
    try:
        user = authenticate_user(db, data.email, data.password)
    except InvalidCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from None
    except UserInactiveError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from None

    user_agent, ip_address = get_client_info(request)
    access_token, refresh_token = create_tokens(
        db, user, user_agent=user_agent, ip_address=ip_address
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=get_token_expiry_seconds(),
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    data: TokenRefresh,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Refresh access token using refresh token.

    Implements refresh token rotation: the old refresh token is
    invalidated and a new one is issued.
    """
    try:
        user_agent, ip_address = get_client_info(request)
        access_token, new_refresh_token, _ = refresh_tokens(
            db,
            data.refresh_token,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in=get_token_expiry_seconds(),
        )
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from None


@router.post("/logout", response_model=MessageResponse)
def logout(
    data: LogoutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Logout user by revoking refresh token(s)."""
    if data.all_sessions:
        count = revoke_all_user_tokens(db, user.id)
        return MessageResponse(message=f"Logged out from all {count} sessions")
    else:
        revoked = revoke_refresh_token(db, data.refresh_token)
        if revoked:
            return MessageResponse(message="Logged out successfully")
        else:
            return MessageResponse(message="Token already revoked or not found")


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)) -> User:
    """Get current user profile."""
    return user
