"""
FastAPI dependencies for database and Redis.
"""

import os
from collections.abc import Generator
from typing import Any

import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# --- Database Setup (Sync SQLAlchemy + psycopg2) ---
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/drugdiscovery"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 1},  # 1 second timeout
)

SessionLocal = sessionmaker(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session with 1s connect timeout."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Redis Setup ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def get_redis() -> Generator[Any, None, None]:
    """Yield a Redis client with 1s timeout."""
    client = redis.from_url(
        REDIS_URL,
        socket_timeout=1,
        socket_connect_timeout=1,
    )
    try:
        yield client
    finally:
        client.close()
