"""Pydantic schemas for authentication."""

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from apps.api.auth.models import UserRole

# =============================================================================
# Request Schemas
# =============================================================================


class UserRegister(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str
    full_name: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain an uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain a lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain a digit")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        """Validate full name."""
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Full name must be at least 2 characters")
        return v


class UserLogin(BaseModel):
    """User login request."""

    email: EmailStr
    password: str


class TokenRefresh(BaseModel):
    """Token refresh request."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Logout request."""

    refresh_token: str
    all_sessions: bool = False


# =============================================================================
# Response Schemas
# =============================================================================


class UserResponse(BaseModel):
    """User response (public info)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    is_active: bool
    is_verified: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """Token response after login/refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class LoginResponse(BaseModel):
    """Login response with tokens and user info."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str


# =============================================================================
# API Key Schemas
# =============================================================================


class ApiKeyCreate(BaseModel):
    """API key creation request."""

    name: str
    role: UserRole = UserRole.VIEWER
    scopes: list[str] | None = None  # e.g., ["read:molecules", "write:predictions"]
    expires_in_days: int | None = None  # None = never expires

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate API key name."""
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        if len(v) > 255:
            raise ValueError("Name must be at most 255 characters")
        return v


class ApiKeyResponse(BaseModel):
    """API key response (without the actual key)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    key_prefix: str
    role: UserRole
    scopes: list[str] | None = None
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    created_by_email: str | None = None


class ApiKeyCreatedResponse(BaseModel):
    """Response when API key is created (includes plaintext key ONCE)."""

    id: UUID
    name: str
    key: str  # Full key - ONLY shown once!
    key_prefix: str
    role: UserRole
    scopes: list[str] | None = None
    expires_at: datetime | None
    created_at: datetime
    warning: str = "Store this key securely. It will not be shown again."


# =============================================================================
# Password Reset Schemas
# =============================================================================


class ForgotPasswordRequest(BaseModel):
    """Password reset request (forgot password)."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Password reset with token."""

    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength (same rules as registration)."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain an uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain a lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain a digit")
        return v


# =============================================================================
# Internal Schemas
# =============================================================================


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str  # user_id
    role: str
    exp: int
    iat: int
    jti: str  # unique token id
