"""FastAPI dependencies for authentication and authorization."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.auth.models import Membership, Organization, Team, User, UserRole
from apps.api.auth.security import decode_access_token
from apps.api.db import get_db

# Bearer token scheme
bearer_scheme = HTTPBearer(auto_error=False)


# =============================================================================
# User Authentication
# =============================================================================


def get_user_by_id(db: Session, user_id: UUID) -> User | None:
    """Get user by ID."""
    stmt = select(User).where(User.id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Get current authenticated user from JWT token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_access_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_id(db, UUID(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Get current user if authenticated, None otherwise."""
    if not credentials:
        return None

    try:
        return get_current_user(credentials, db)
    except HTTPException:
        return None


# =============================================================================
# Organization & Membership Access
# =============================================================================


def get_membership(db: Session, user_id: UUID, org_id: UUID) -> Membership | None:
    """Get user's membership in an organization."""
    stmt = select(Membership).where(
        Membership.user_id == user_id,
        Membership.organization_id == org_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def get_organization(db: Session, org_id: UUID) -> Organization | None:
    """Get organization by ID."""
    stmt = select(Organization).where(Organization.id == org_id)
    return db.execute(stmt).scalar_one_or_none()


def get_team(db: Session, team_id: UUID) -> Team | None:
    """Get team by ID."""
    stmt = select(Team).where(Team.id == team_id)
    return db.execute(stmt).scalar_one_or_none()


class OrgContext:
    """Context object containing org access information."""

    def __init__(
        self,
        user: User,
        organization: Organization,
        membership: Membership,
    ):
        self.user = user
        self.organization = organization
        self.membership = membership
        self.role = membership.role

    @property
    def org_id(self) -> UUID:
        return self.organization.id  # type: ignore[return-value]

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def is_researcher(self) -> bool:
        return self.role in (UserRole.ADMIN, UserRole.RESEARCHER)

    @property
    def is_viewer(self) -> bool:
        return self.role in (UserRole.ADMIN, UserRole.RESEARCHER, UserRole.VIEWER)


class TeamContext(OrgContext):
    """Context object containing team access information."""

    def __init__(
        self,
        user: User,
        organization: Organization,
        membership: Membership,
        team: Team,
    ):
        super().__init__(user, organization, membership)
        self.team = team

    @property
    def team_id(self) -> UUID:
        return self.team.id  # type: ignore[return-value]


# =============================================================================
# Tenant Isolation Dependencies
# =============================================================================


def require_org_access(
    org_id: Annotated[UUID, Path(description="Organization ID")],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgContext:
    """Require user has access to the organization.

    Usage:
        @app.get("/orgs/{org_id}/projects")
        def list_projects(ctx: OrgContext = Depends(require_org_access)):
            # ctx.user, ctx.organization, ctx.membership, ctx.role available
            return get_projects(ctx.org_id)
    """
    # Check org exists
    org = get_organization(db, org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    if not org.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is inactive",
        )

    # Check membership
    membership = get_membership(db, user.id, org_id)  # type: ignore[arg-type]
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organization",
        )

    return OrgContext(user=user, organization=org, membership=membership)


def require_team_access(
    org_id: Annotated[UUID, Path(description="Organization ID")],
    team_id: Annotated[UUID, Path(description="Team ID")],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamContext:
    """Require user has access to the team within an organization.

    Usage:
        @app.get("/orgs/{org_id}/teams/{team_id}/members")
        def list_team_members(ctx: TeamContext = Depends(require_team_access)):
            return get_team_members(ctx.team_id)
    """
    # First check org access
    org_ctx = require_org_access(org_id, user, db)

    # Check team exists and belongs to org
    team = get_team(db, team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found",
        )

    if team.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found in this organization",
        )

    # Check user is in this team (or is admin)
    if org_ctx.membership.role != UserRole.ADMIN:
        if org_ctx.membership.team_id != team_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of this team",
            )

    return TeamContext(
        user=user,
        organization=org_ctx.organization,
        membership=org_ctx.membership,
        team=team,
    )


# =============================================================================
# Role-Based Access Control (within Org context)
# =============================================================================


def require_org_role(
    allowed_roles: list[UserRole],
) -> Callable[[OrgContext], OrgContext]:
    """Dependency factory that requires specific roles within an organization.

    Usage:
        @app.post("/orgs/{org_id}/projects")
        def create_project(
            ctx: OrgContext = Depends(require_org_role([UserRole.ADMIN, UserRole.RESEARCHER]))
        ):
            ...
    """

    def role_checker(ctx: OrgContext = Depends(require_org_access)) -> OrgContext:
        if ctx.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{ctx.role.value}' cannot perform this action. "
                f"Required: {[r.value for r in allowed_roles]}",
            )
        return ctx

    return role_checker


# Convenience dependencies for common role patterns
require_org_admin = require_org_role([UserRole.ADMIN])
require_org_researcher = require_org_role([UserRole.ADMIN, UserRole.RESEARCHER])
require_org_viewer = require_org_role([UserRole.ADMIN, UserRole.RESEARCHER, UserRole.VIEWER])
