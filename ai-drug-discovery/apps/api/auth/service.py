"""Authentication service layer."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.auth.models import RefreshToken, User, UserRole
from apps.api.auth.schemas import UserRegister
from apps.api.auth.security import (
    create_access_token,
    generate_refresh_token,
    get_access_token_expiry,
    get_refresh_token_expiry,
    hash_password,
    hash_token,
    verify_password,
)


class AuthError(Exception):
    """Base authentication error."""

    pass


class InvalidCredentialsError(AuthError):
    """Invalid email or password."""

    pass


class UserExistsError(AuthError):
    """User already exists."""

    pass


class InvalidTokenError(AuthError):
    """Invalid or expired token."""

    pass


class UserInactiveError(AuthError):
    """User account is inactive."""

    pass


# =============================================================================
# User Operations
# =============================================================================


def get_user_by_email(db: Session, email: str) -> User | None:
    """Get user by email address."""
    stmt = select(User).where(User.email == email)
    return db.execute(stmt).scalar_one_or_none()


def get_user_by_id(db: Session, user_id: UUID) -> User | None:
    """Get user by ID."""
    stmt = select(User).where(User.id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def create_user(db: Session, data: UserRegister) -> User:
    """Create a new user."""
    # Check if user exists
    existing = get_user_by_email(db, data.email)
    if existing:
        raise UserExistsError("Email already registered")

    # Create user
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=UserRole.VIEWER,  # Default role
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return user


# =============================================================================
# Authentication Operations
# =============================================================================


def authenticate_user(db: Session, email: str, password: str) -> User:
    """Authenticate user with email and password."""
    user = get_user_by_email(db, email)

    if not user:
        raise InvalidCredentialsError("Invalid email or password")

    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("Invalid email or password")

    if not user.is_active:
        raise UserInactiveError("User account is inactive")

    return user


# =============================================================================
# Token Operations
# =============================================================================


def create_tokens(
    db: Session,
    user: User,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, str]:
    """Create access and refresh tokens for a user.

    Returns:
        Tuple of (access_token, refresh_token)
    """
    # Create access token
    access_token = create_access_token(user.id, user.role.value)

    # Create refresh token
    refresh_token = generate_refresh_token()

    # Store hashed refresh token in DB
    token_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        expires_at=get_refresh_token_expiry(),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(token_record)
    db.commit()

    return access_token, refresh_token


def refresh_tokens(
    db: Session,
    refresh_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, str, User]:
    """Refresh access token using refresh token.

    Implements refresh token rotation: old token is revoked,
    new refresh token is issued.

    Returns:
        Tuple of (access_token, new_refresh_token, user)
    """
    token_hash = hash_token(refresh_token)

    # Find token in DB
    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    token_record = db.execute(stmt).scalar_one_or_none()

    if not token_record:
        raise InvalidTokenError("Invalid refresh token")

    if not token_record.is_valid:
        raise InvalidTokenError("Refresh token expired or revoked")

    # Get user
    user = get_user_by_id(db, token_record.user_id)
    if not user or not user.is_active:
        raise InvalidTokenError("User not found or inactive")

    # Revoke old refresh token (rotation)
    token_record.revoked_at = datetime.utcnow()

    # Create new tokens
    access_token = create_access_token(user.id, user.role.value)
    new_refresh_token = generate_refresh_token()

    # Store new refresh token
    new_token_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(new_refresh_token),
        expires_at=get_refresh_token_expiry(),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(new_token_record)
    db.commit()

    return access_token, new_refresh_token, user


def revoke_refresh_token(db: Session, refresh_token: str) -> bool:
    """Revoke a single refresh token.

    Returns:
        True if token was found and revoked, False otherwise.
    """
    token_hash = hash_token(refresh_token)

    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    token_record = db.execute(stmt).scalar_one_or_none()

    if token_record and token_record.revoked_at is None:
        token_record.revoked_at = datetime.utcnow()
        db.commit()
        return True

    return False


def revoke_all_user_tokens(db: Session, user_id: UUID) -> int:
    """Revoke all refresh tokens for a user.

    Returns:
        Number of tokens revoked.
    """
    stmt = select(RefreshToken).where(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked_at.is_(None),
    )
    tokens = db.execute(stmt).scalars().all()

    now = datetime.utcnow()
    for token in tokens:
        token.revoked_at = now

    db.commit()
    return len(tokens)


def get_token_expiry_seconds() -> int:
    """Get access token expiry in seconds."""
    return get_access_token_expiry()
