from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import app.indexer.config as cfg

def _make_engine():
    url = f"sqlite:///{cfg.DB_PATH}"
    return create_engine(url, connect_args={"check_same_thread": False})

engine = _make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
