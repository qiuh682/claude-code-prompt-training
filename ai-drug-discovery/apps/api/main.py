"""
FastAPI application entrypoint.
"""

from fastapi import FastAPI

from apps.api.routers import auth, db_check, health, projects, redis_check

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
