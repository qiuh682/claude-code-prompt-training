"""
Database connection setup (sync SQLAlchemy + psycopg2).
"""

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# --- Configuration ---
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5433/drugdiscovery",
)

# --- Engine with short timeouts ---
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 1},  # 1 second connect timeout
)

SessionLocal = sessionmaker(bind=engine)


# --- Dependency ---
def get_db() -> Generator[Session, None, None]:
    """Yield a database session. Use as FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
