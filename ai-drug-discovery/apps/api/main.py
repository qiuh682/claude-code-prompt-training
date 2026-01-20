"""
FastAPI application entrypoint.
"""

from fastapi import FastAPI

from apps.api.routers import health

app = FastAPI(
    title="AI Drug Discovery Platform",
    version="0.1.0",
)

# Include health router
app.include_router(health.router)
