"""
Example protected routes demonstrating multi-tenant authorization.

This module shows how to use the authorization dependencies:
- require_org_access: Basic org membership check
- require_org_role: Role-based access within org
- require_org_admin/researcher/viewer: Convenience shortcuts
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import (
    OrgContext,
    require_org_access,
    require_org_admin,
    require_org_researcher,
    require_org_role,
)
from apps.api.auth.models import UserRole
from apps.api.db import get_db

router = APIRouter(prefix="/orgs/{org_id}/projects", tags=["Projects"])


# =============================================================================
# Schemas
# =============================================================================


class ProjectCreate(BaseModel):
    """Project creation request."""

    name: str
    description: str | None = None


class ProjectUpdate(BaseModel):
    """Project update request."""

    name: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    """Project response."""

    id: str
    name: str
    description: str | None
    organization_id: str
    created_by: str


# =============================================================================
# Routes: Viewer can read
# =============================================================================


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    ctx: OrgContext = Depends(require_org_access),
    db: Session = Depends(get_db),
) -> list[ProjectResponse]:
    """List all projects in the organization.

    Access: Any org member (admin, researcher, viewer)

    The ctx.org_id ensures we only query this organization's data.
    """
    # In real code: query projects filtered by ctx.org_id
    # projects = db.query(Project).filter(Project.organization_id == ctx.org_id).all()

    # Example response
    return [
        ProjectResponse(
            id="proj-123",
            name="Drug Candidate Analysis",
            description="ML-based drug candidate screening",
            organization_id=str(ctx.org_id),
            created_by=str(ctx.user.id),
        )
    ]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: UUID,
    ctx: OrgContext = Depends(require_org_access),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Get a specific project.

    Access: Any org member (admin, researcher, viewer)

    IMPORTANT: Always filter by org_id to prevent cross-tenant access!
    """
    # In real code:
    # project = db.query(Project).filter(
    #     Project.id == project_id,
    #     Project.organization_id == ctx.org_id  # CRITICAL: tenant isolation
    # ).first()
    # if not project:
    #     raise HTTPException(status_code=404, detail="Project not found")

    return ProjectResponse(
        id=str(project_id),
        name="Drug Candidate Analysis",
        description="ML-based drug candidate screening",
        organization_id=str(ctx.org_id),
        created_by=str(ctx.user.id),
    )


# =============================================================================
# Routes: Researcher can create/edit
# =============================================================================


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    ctx: OrgContext = Depends(require_org_researcher),  # Admin or Researcher
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Create a new project.

    Access: Admin or Researcher only

    Viewers will get 403 Forbidden.
    """
    # In real code:
    # project = Project(
    #     name=data.name,
    #     description=data.description,
    #     organization_id=ctx.org_id,  # Always set org from context
    #     created_by=ctx.user.id,
    # )
    # db.add(project)
    # db.commit()

    return ProjectResponse(
        id="proj-new-123",
        name=data.name,
        description=data.description,
        organization_id=str(ctx.org_id),
        created_by=str(ctx.user.id),
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: UUID,
    data: ProjectUpdate,
    ctx: OrgContext = Depends(require_org_researcher),  # Admin or Researcher
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Update a project.

    Access: Admin or Researcher only
    """
    # In real code: fetch project with org_id filter, update fields

    return ProjectResponse(
        id=str(project_id),
        name=data.name or "Updated Project",
        description=data.description,
        organization_id=str(ctx.org_id),
        created_by=str(ctx.user.id),
    )


# =============================================================================
# Routes: Admin only
# =============================================================================


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: UUID,
    ctx: OrgContext = Depends(require_org_admin),  # Admin only
    db: Session = Depends(get_db),
) -> None:
    """Delete a project.

    Access: Admin only

    Researchers and Viewers will get 403 Forbidden.
    """
    # In real code:
    # project = db.query(Project).filter(
    #     Project.id == project_id,
    #     Project.organization_id == ctx.org_id
    # ).first()
    # if project:
    #     db.delete(project)
    #     db.commit()
    pass


# =============================================================================
# Routes: Custom role check example
# =============================================================================


@router.post("/{project_id}/archive")
def archive_project(
    project_id: UUID,
    ctx: OrgContext = Depends(
        require_org_role([UserRole.ADMIN, UserRole.RESEARCHER])
    ),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Archive a project (custom role check example).

    Access: Admin or Researcher (explicit role list)
    """
    return {"status": "archived", "project_id": str(project_id)}


# =============================================================================
# Example: Checking role within route logic
# =============================================================================


@router.get("/{project_id}/audit-log")
def get_audit_log(
    project_id: UUID,
    ctx: OrgContext = Depends(require_org_access),
    db: Session = Depends(get_db),
) -> dict:
    """Get project audit log.

    Access: Any member can view, but admins see more details.

    This shows how to check role within the route for conditional logic.
    """
    base_log = {
        "project_id": str(project_id),
        "events": [
            {"action": "created", "timestamp": "2024-01-15T10:00:00Z"},
            {"action": "updated", "timestamp": "2024-01-16T14:30:00Z"},
        ],
    }

    # Admins see additional sensitive info
    if ctx.is_admin:
        base_log["sensitive_events"] = [
            {"action": "api_key_rotated", "timestamp": "2024-01-17T09:00:00Z"},
        ]

    return base_log
