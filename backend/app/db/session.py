from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.effective_database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> dict[str, Any]:
    """Tests connectivity to PostgreSQL and returns status."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();")).scalar()
            return {
                "status": "connected",
                "database": settings.POSTGRES_DB,
                "user": settings.POSTGRES_USER,
                "host": settings.POSTGRES_HOST,
                "port": settings.POSTGRES_PORT,
                "version": str(result),
            }
    except Exception as e:
        return {
            "status": "error",
            "database": settings.POSTGRES_DB,
            "host": settings.POSTGRES_HOST,
            "port": settings.POSTGRES_PORT,
            "error": str(e),
        }
