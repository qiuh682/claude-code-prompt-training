"""Base model with common fields and mixins."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from db.base import Base


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AuditMixin(TimestampMixin):
    """Mixin that adds audit fields (created_by, updated_by) plus timestamps."""

    @declared_attr
    def created_by(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=False,
        )

    @declared_attr
    def updated_by(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(
            UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        )


class SoftDeleteMixin:
    """Mixin that adds soft delete capability via deleted_at timestamp."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    @property
    def is_deleted(self) -> bool:
        """Check if record is soft-deleted."""
        return self.deleted_at is not None


class BaseModel(Base, TimestampMixin):
    """Base model with UUID primary key and timestamps."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )


class AuditedModel(Base, AuditMixin, SoftDeleteMixin):
    """Base model with UUID primary key, audit fields, and soft delete."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
