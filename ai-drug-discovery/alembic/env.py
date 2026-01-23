"""Alembic migration environment configuration (sync SQLAlchemy)."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Import Base first
from db.base import Base

# Import all models here so Alembic can detect them for autogenerate
# Auth models
from apps.api.auth.models import (  # noqa: F401
    ApiKey,
    Membership,
    Organization,
    PasswordResetToken,
    RefreshToken,
    Team,
    User,
)

# Base model mixins
from db.models.base_model import AuditedModel, BaseModel  # noqa: F401

# Discovery domain models (Task 1.3)
from db.models.discovery import (  # noqa: F401
    Assay,
    Molecule,
    MoleculeTarget,
    Prediction,
    Project,
    ProjectMolecule,
    ProjectTarget,
    Target,
)

# ML Model Registry models (Task 3.1)
from db.models.ml_registry import (  # noqa: F401
    MLModel,
    MLModelArtifact,
    MLModelDeployment,
    MLModelLineage,
    MLModelMetrics,
    MLModelVersion,
)

# this is the Alembic Config object
config = context.config

# Get database URL from environment (takes precedence) or alembic.ini
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (sync).

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
