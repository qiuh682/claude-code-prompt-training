"""
FastAPI application entrypoint.
"""

from fastapi import FastAPI

from apps.api.routers import db_check, health, redis_check

app = FastAPI(
    title="AI Drug Discovery Platform",
    version="0.1.0",
)

# Include routers
app.include_router(health.router)
app.include_router(db_check.router)
app.include_router(redis_check.router)
