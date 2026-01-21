"""Base model with common fields and mixins."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, TypeVar

from sqlalchemy import DateTime, ForeignKey, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, declared_attr, mapped_column

from db.base import Base

if TYPE_CHECKING:
    from sqlalchemy.sql import Select

# Type variable for generic query methods
T = TypeVar("T", bound="SoftDeleteMixin")


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
    """
    Mixin that adds soft delete capability via deleted_at timestamp.

    Usage:
        # Soft delete a record
        molecule.soft_delete(db)

        # Check if deleted
        if molecule.is_deleted:
            ...

        # Restore a record
        molecule.restore(db)

    Query Patterns:
        # Active records only (recommended default)
        stmt = select(Molecule).where(Molecule.deleted_at.is_(None))

        # Or use the class method:
        stmt = Molecule.active_query()

        # Include deleted records (admin/audit)
        stmt = select(Molecule)

        # Only deleted records (recovery UI)
        stmt = select(Molecule).where(Molecule.deleted_at.isnot(None))
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    @property
    def is_deleted(self) -> bool:
        """Check if record is soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(self, db: Session) -> None:
        """
        Soft delete this record by setting deleted_at to current time.

        Args:
            db: SQLAlchemy session

        Example:
            molecule = db.get(Molecule, molecule_id)
            molecule.soft_delete(db)
        """
        self.deleted_at = datetime.now(UTC)
        db.add(self)
        db.flush()

    def restore(self, db: Session) -> None:
        """
        Restore a soft-deleted record by clearing deleted_at.

        Args:
            db: SQLAlchemy session

        Example:
            molecule = db.get(Molecule, molecule_id)
            molecule.restore(db)
        """
        self.deleted_at = None
        db.add(self)
        db.flush()

    @classmethod
    def active_query(cls: type[T]) -> "Select[tuple[T]]":
        """
        Return a select statement that excludes soft-deleted records.

        Usage:
            stmt = Molecule.active_query().where(Molecule.org_id == org_id)
            molecules = db.execute(stmt).scalars().all()

        Returns:
            SQLAlchemy Select statement with deleted_at IS NULL filter
        """
        return select(cls).where(cls.deleted_at.is_(None))

    @classmethod
    def deleted_query(cls: type[T]) -> "Select[tuple[T]]":
        """
        Return a select statement for only soft-deleted records.

        Useful for admin recovery UIs.

        Returns:
            SQLAlchemy Select statement with deleted_at IS NOT NULL filter
        """
        return select(cls).where(cls.deleted_at.isnot(None))


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
