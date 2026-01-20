"""SQLAlchemy models for authentication and multi-tenancy."""

import enum
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from db.base import Base

# =============================================================================
# Enums
# =============================================================================


class UserRole(str, enum.Enum):
    """User roles for RBAC within an organization."""

    ADMIN = "admin"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


class OrgPlan(str, enum.Enum):
    """Organization subscription plan."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# =============================================================================
# User Model
# =============================================================================


class User(Base):
    """User account model."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    refresh_tokens = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    memberships = relationship(
        "Membership", back_populates="user", cascade="all, delete-orphan"
    )
    api_keys = relationship("ApiKey", back_populates="created_by")

    def __repr__(self) -> str:
        return f"<User {self.email}>"


# =============================================================================
# Organization & Team Models
# =============================================================================


class Organization(Base):
    """Organization (tenant) model."""

    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    plan = Column(Enum(OrgPlan), default=OrgPlan.FREE, nullable=False)
    rate_limit_rpm = Column(Integer, default=60, nullable=False)  # requests per minute
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    teams = relationship(
        "Team", back_populates="organization", cascade="all, delete-orphan"
    )
    memberships = relationship(
        "Membership", back_populates="organization", cascade="all, delete-orphan"
    )
    api_keys = relationship(
        "ApiKey", back_populates="organization", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Organization {self.slug}>"


class Team(Base):
    """Team within an organization."""

    __tablename__ = "teams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Unique team name within org
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_team_org_name"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="teams")
    memberships = relationship(
        "Membership", back_populates="team", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Team {self.name}>"


# =============================================================================
# Membership Model (User <-> Org/Team with Role)
# =============================================================================


class Membership(Base):
    """User membership in an organization with role."""

    __tablename__ = "memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id = Column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
    )
    role = Column(Enum(UserRole), nullable=False, default=UserRole.VIEWER)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # User can only have one membership per organization
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),
    )

    # Relationships
    user = relationship("User", back_populates="memberships")
    organization = relationship("Organization", back_populates="memberships")
    team = relationship("Team", back_populates="memberships")

    def __repr__(self) -> str:
        return f"<Membership user={self.user_id} org={self.organization_id} role={self.role}>"


# =============================================================================
# API Key Model
# =============================================================================


class ApiKey(Base):
    """API key for programmatic access."""

    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Key identification
    name = Column(String(255), nullable=False)
    key_prefix = Column(String(12), nullable=False)  # e.g., "sk_live_abc1"
    key_hash = Column(String(255), nullable=False, index=True)

    # Permissions
    role = Column(Enum(UserRole), nullable=False, default=UserRole.VIEWER)
    scopes = Column(Text, nullable=True)  # JSON array of scopes, e.g., '["read:molecules"]'

    # Rate limiting (overrides org default if set)
    rate_limit_rpm = Column(Integer, nullable=True)

    # Lifecycle
    expires_at = Column(DateTime, nullable=True)  # None = never expires
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="api_keys")
    created_by = relationship("User", back_populates="api_keys")

    @property
    def is_valid(self) -> bool:
        """Check if API key is valid (not expired, not revoked)."""
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at < datetime.utcnow():
            return False
        return True

    def __repr__(self) -> str:
        return f"<ApiKey {self.key_prefix}... org={self.organization_id}>"


# =============================================================================
# Refresh Token Model
# =============================================================================


class RefreshToken(Base):
    """Refresh token for JWT authentication."""

    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash = Column(String(255), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Session metadata
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 max length

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")

    @property
    def is_valid(self) -> bool:
        """Check if token is valid (not expired, not revoked)."""
        now = datetime.utcnow()
        return self.revoked_at is None and self.expires_at > now

    def __repr__(self) -> str:
        return f"<RefreshToken {self.id}>"


# =============================================================================
# Password Reset Token Model
# =============================================================================


class PasswordResetToken(Base):
    """Token for password reset functionality."""

    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash = Column(String(255), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)  # Set when token is used
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", backref="password_reset_tokens")

    @property
    def is_valid(self) -> bool:
        """Check if token is valid (not expired, not used)."""
        now = datetime.utcnow()
        return self.used_at is None and self.expires_at > now

    def __repr__(self) -> str:
        return f"<PasswordResetToken {self.id}>"
