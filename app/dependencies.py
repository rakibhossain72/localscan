"""FastAPI dependency providers."""
from typing import Generator
from app.db.session import SessionLocal


def get_db() -> Generator:
    """Yield a database session and ensure it is closed after use."""
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()
