"""API key management routes."""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import OrgContext, require_org_admin
from apps.api.auth.models import ApiKey
from apps.api.auth.schemas import ApiKeyCreate, ApiKeyCreatedResponse, ApiKeyResponse
from apps.api.auth.service import create_api_key, get_api_keys_by_org, revoke_api_key
from apps.api.db import get_db
from apps.api.ratelimit import rate_limit_default

router = APIRouter(prefix="/orgs/{org_id}/api-keys", tags=["API Keys"])


def _api_key_to_response(api_key: ApiKey) -> ApiKeyResponse:
    """Convert ApiKey model to response schema."""
    scopes = None
    if api_key.scopes:
        scopes = json.loads(api_key.scopes)

    created_by_email = None
    if api_key.created_by:
        created_by_email = api_key.created_by.email

    return ApiKeyResponse(
        id=api_key.id,  # type: ignore[arg-type]
        name=api_key.name,  # type: ignore[arg-type]
        key_prefix=api_key.key_prefix,  # type: ignore[arg-type]
        role=api_key.role,  # type: ignore[arg-type]
        scopes=scopes,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,  # type: ignore[arg-type]
        created_by_email=created_by_email,
    )


@router.post(
    "",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_default)],
)
def create_key(
    data: ApiKeyCreate,
    ctx: OrgContext = Depends(require_org_admin),
    db: Session = Depends(get_db),
) -> ApiKeyCreatedResponse:
    """Create a new API key for the organization.

    Access: Admin only

    WARNING: The plaintext key is only returned once at creation.
    Store it securely - it cannot be retrieved again.
    """
    api_key, plaintext_key = create_api_key(
        db=db,
        org_id=ctx.org_id,
        created_by_id=ctx.user.id,  # type: ignore[arg-type]
        data=data,
    )

    scopes = None
    if api_key.scopes:
        scopes = json.loads(api_key.scopes)

    return ApiKeyCreatedResponse(
        id=api_key.id,  # type: ignore[arg-type]
        name=api_key.name,  # type: ignore[arg-type]
        key=plaintext_key,
        key_prefix=api_key.key_prefix,  # type: ignore[arg-type]
        role=api_key.role,  # type: ignore[arg-type]
        scopes=scopes,
        expires_at=api_key.expires_at,
        created_at=api_key.created_at,  # type: ignore[arg-type]
    )


@router.get(
    "",
    response_model=list[ApiKeyResponse],
    dependencies=[Depends(rate_limit_default)],
)
def list_keys(
    ctx: OrgContext = Depends(require_org_admin),
    db: Session = Depends(get_db),
) -> list[ApiKeyResponse]:
    """List all active API keys for the organization.

    Access: Admin only
    """
    api_keys = get_api_keys_by_org(db, ctx.org_id)
    return [_api_key_to_response(key) for key in api_keys]


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit_default)],
)
def revoke_key(
    key_id: UUID,
    ctx: OrgContext = Depends(require_org_admin),
    db: Session = Depends(get_db),
) -> None:
    """Revoke an API key.

    Access: Admin only

    The key will immediately stop working.
    """
    revoked = revoke_api_key(db, key_id, ctx.org_id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or already revoked",
        )
