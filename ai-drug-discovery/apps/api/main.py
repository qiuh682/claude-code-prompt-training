"""
FastAPI application entrypoint.
"""

from fastapi import FastAPI

from apps.api.routers import api_keys, auth, db_check, health, projects, redis_check, uploads

app = FastAPI(
    title="AI Drug Discovery Platform",
    version="0.1.0",
)

# Include routers
app.include_router(health.router)
app.include_router(db_check.router)
app.include_router(redis_check.router)
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(api_keys.router)
app.include_router(uploads.router, prefix="/api/v1/uploads", tags=["uploads"])
