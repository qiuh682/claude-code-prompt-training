"""Authentication service layer."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.auth.models import ApiKey, RefreshToken, User
from apps.api.auth.schemas import ApiKeyCreate, UserRegister
from apps.api.auth.security import (
    create_access_token,
    generate_api_key,
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

    # Create user (role is now per-org via Membership, not on User)
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
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

    Note: JWT contains user_id only. Role is determined per-org at access time.

    Returns:
        Tuple of (access_token, refresh_token)
    """
    # Create access token (role is "user" - actual role checked per-org)
    access_token = create_access_token(user.id, "user")

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

    # Create new tokens (role is "user" - actual role checked per-org)
    access_token = create_access_token(user.id, "user")
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


# =============================================================================
# API Key Operations
# =============================================================================


class ApiKeyError(AuthError):
    """API key related error."""

    pass


def create_api_key(
    db: Session,
    org_id: UUID,
    created_by_id: UUID,
    data: ApiKeyCreate,
) -> tuple[ApiKey, str]:
    """Create a new API key for an organization.

    Returns:
        Tuple of (api_key_record, plaintext_key)
        The plaintext key is only available at creation time!
    """
    import json
    from datetime import timedelta

    # Generate the key
    plaintext_key, key_prefix = generate_api_key()

    # Calculate expiry
    expires_at = None
    if data.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=data.expires_in_days)

    # Store scopes as JSON
    scopes_json = json.dumps(data.scopes) if data.scopes else None

    # Create API key record
    api_key = ApiKey(
        organization_id=org_id,
        created_by_id=created_by_id,
        name=data.name,
        key_prefix=key_prefix,
        key_hash=hash_token(plaintext_key),
        role=data.role,
        scopes=scopes_json,
        expires_at=expires_at,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return api_key, plaintext_key


def get_api_key_by_hash(db: Session, key_hash: str) -> ApiKey | None:
    """Get API key by its hash."""
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
    return db.execute(stmt).scalar_one_or_none()


def get_api_keys_by_org(db: Session, org_id: UUID) -> list[ApiKey]:
    """Get all API keys for an organization."""
    stmt = (
        select(ApiKey)
        .where(ApiKey.organization_id == org_id, ApiKey.revoked_at.is_(None))
        .order_by(ApiKey.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def get_api_key_by_id(db: Session, key_id: UUID, org_id: UUID) -> ApiKey | None:
    """Get API key by ID within an organization."""
    stmt = select(ApiKey).where(
        ApiKey.id == key_id,
        ApiKey.organization_id == org_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def revoke_api_key(db: Session, key_id: UUID, org_id: UUID) -> bool:
    """Revoke an API key.

    Returns:
        True if key was found and revoked, False otherwise.
    """
    api_key = get_api_key_by_id(db, key_id, org_id)

    if api_key and api_key.revoked_at is None:
        api_key.revoked_at = datetime.utcnow()
        db.commit()
        return True

    return False


def update_api_key_last_used(db: Session, api_key: ApiKey) -> None:
    """Update the last_used_at timestamp for an API key."""
    api_key.last_used_at = datetime.utcnow()
    db.commit()


def validate_api_key(db: Session, plaintext_key: str) -> ApiKey | None:
    """Validate an API key and return the key record if valid.

    Also updates the last_used_at timestamp.

    Returns:
        ApiKey record if valid, None otherwise.
    """
    key_hash = hash_token(plaintext_key)
    api_key = get_api_key_by_hash(db, key_hash)

    if not api_key:
        return None

    if not api_key.is_valid:
        return None

    # Update last used timestamp
    update_api_key_last_used(db, api_key)

    return api_key
