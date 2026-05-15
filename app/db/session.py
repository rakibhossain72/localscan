"""SQLAlchemy engine and session factory."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.indexer.config as cfg


def _make_engine():
    url = f"sqlite:///{cfg.DB_PATH}"
    return create_engine(url, connect_args={"check_same_thread": False})


engine = _make_engine()
session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Alias kept for compatibility with code that imports SessionLocal by name
SessionLocal = session_local


def get_db():
    """Yield a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
