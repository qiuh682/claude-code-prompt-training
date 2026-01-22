"""
ARQ worker for background upload processing.

ARQ is a fast job queue library using Redis, designed for async Python.
Alternative to Celery for async FastAPI applications.

Usage:
    # Start worker
    arq apps.api.uploads.worker.WorkerSettings

    # Or with custom redis
    arq apps.api.uploads.worker.WorkerSettings --redis redis://localhost:6379/1
"""

import asyncio
import logging
import uuid
from datetime import timedelta
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from apps.api.config import get_settings
from apps.api.uploads.service import UploadService
from apps.api.uploads.tasks import UploadProcessor
from db.session import async_session_factory
from packages.shared.storage import get_storage_backend

logger = logging.getLogger(__name__)


# =============================================================================
# Job Functions
# =============================================================================


async def validate_upload_job(
    ctx: dict[str, Any],
    upload_id: str,
    organization_id: str,
) -> dict[str, Any]:
    """
    Background job to validate an upload.

    Args:
        ctx: ARQ context (contains redis connection)
        upload_id: Upload UUID as string
        organization_id: Organization UUID as string

    Returns:
        Job result dict
    """
    logger.info(f"Starting validation for upload {upload_id}")

    async with async_session_factory() as db:
        storage = get_storage_backend()
        service = UploadService(db, storage)

        upload = await service.get_upload(
            uuid.UUID(upload_id),
            uuid.UUID(organization_id),
        )

        if not upload:
            logger.error(f"Upload {upload_id} not found")
            return {"status": "error", "message": "Upload not found"}

        try:
            processor = UploadProcessor(db, service)
            await processor.process_validation(upload)
            logger.info(f"Validation completed for upload {upload_id}")
            return {"status": "success", "upload_id": upload_id}
        except Exception as e:
            logger.exception(f"Validation failed for upload {upload_id}")
            return {"status": "error", "message": str(e)}


async def process_upload_job(
    ctx: dict[str, Any],
    upload_id: str,
    organization_id: str,
) -> dict[str, Any]:
    """
    Background job to process (insert molecules) for a confirmed upload.

    Args:
        ctx: ARQ context
        upload_id: Upload UUID as string
        organization_id: Organization UUID as string

    Returns:
        Job result dict
    """
    logger.info(f"Starting processing for upload {upload_id}")

    async with async_session_factory() as db:
        storage = get_storage_backend()
        service = UploadService(db, storage)

        upload = await service.get_upload(
            uuid.UUID(upload_id),
            uuid.UUID(organization_id),
        )

        if not upload:
            logger.error(f"Upload {upload_id} not found")
            return {"status": "error", "message": "Upload not found"}

        try:
            processor = UploadProcessor(db, service)
            await processor.process_insertion(upload)
            logger.info(f"Processing completed for upload {upload_id}")
            return {"status": "success", "upload_id": upload_id}
        except Exception as e:
            logger.exception(f"Processing failed for upload {upload_id}")
            return {"status": "error", "message": str(e)}


async def cleanup_expired_uploads_job(ctx: dict[str, Any]) -> dict[str, Any]:
    """
    Periodic job to cleanup expired unconfirmed uploads.

    Should be scheduled to run periodically (e.g., every hour).
    """
    logger.info("Starting cleanup of expired uploads")

    async with async_session_factory() as db:
        storage = get_storage_backend()
        service = UploadService(db, storage)

        count = await service.cleanup_expired_uploads()
        logger.info(f"Cleaned up {count} expired uploads")

        return {"status": "success", "cleaned_up": count}


# =============================================================================
# Startup/Shutdown Hooks
# =============================================================================


async def startup(ctx: dict[str, Any]) -> None:
    """Called when worker starts."""
    logger.info("Upload worker starting up")


async def shutdown(ctx: dict[str, Any]) -> None:
    """Called when worker shuts down."""
    logger.info("Upload worker shutting down")


# =============================================================================
# Worker Settings
# =============================================================================


def get_redis_settings() -> RedisSettings:
    """Get Redis settings from config."""
    settings = get_settings()
    # Parse redis URL: redis://localhost:6379/0
    url = settings.redis_url
    if url.startswith("redis://"):
        url = url[8:]
    parts = url.split("/")
    host_port = parts[0]
    database = int(parts[1]) if len(parts) > 1 else 0

    if ":" in host_port:
        host, port = host_port.split(":")
        port = int(port)
    else:
        host = host_port
        port = 6379

    return RedisSettings(
        host=host,
        port=port,
        database=database,
    )


class WorkerSettings:
    """ARQ worker settings."""

    # Job functions
    functions = [
        validate_upload_job,
        process_upload_job,
        cleanup_expired_uploads_job,
    ]

    # Cron jobs (periodic tasks)
    cron_jobs = [
        # Cleanup expired uploads every hour
        # cron(cleanup_expired_uploads_job, hour={0, 1, 2, ...}, minute=0)
    ]

    # Lifecycle hooks
    on_startup = startup
    on_shutdown = shutdown

    # Redis connection
    redis_settings = get_redis_settings()

    # Job settings
    max_jobs = 10  # Max concurrent jobs
    job_timeout = timedelta(minutes=30)  # Max job duration
    max_tries = 3  # Retry failed jobs
    retry_delay = timedelta(seconds=10)


# =============================================================================
# Job Enqueueing Helper
# =============================================================================


_redis_pool: ArqRedis | None = None


async def get_redis_pool() -> ArqRedis:
    """Get or create Redis connection pool for enqueueing jobs."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = await create_pool(get_redis_settings())
    return _redis_pool


async def enqueue_validation_job(
    upload_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> str | None:
    """
    Enqueue a validation job.

    Args:
        upload_id: Upload to validate
        organization_id: Organization ID

    Returns:
        Job ID or None if enqueueing failed
    """
    try:
        redis = await get_redis_pool()
        job = await redis.enqueue_job(
            "validate_upload_job",
            str(upload_id),
            str(organization_id),
        )
        return job.job_id if job else None
    except Exception as e:
        logger.exception(f"Failed to enqueue validation job: {e}")
        return None


async def enqueue_processing_job(
    upload_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> str | None:
    """
    Enqueue a processing job.

    Args:
        upload_id: Upload to process
        organization_id: Organization ID

    Returns:
        Job ID or None if enqueueing failed
    """
    try:
        redis = await get_redis_pool()
        job = await redis.enqueue_job(
            "process_upload_job",
            str(upload_id),
            str(organization_id),
        )
        return job.job_id if job else None
    except Exception as e:
        logger.exception(f"Failed to enqueue processing job: {e}")
        return None
