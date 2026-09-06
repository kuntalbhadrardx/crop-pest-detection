"""SQLAlchemy engine/session setup backed by SQLite."""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(settings.database_url, connect_args=_connect_args)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # keep loaded objects usable after commit
)


def init_db() -> None:
    """Create the database file, upload folders, and all tables."""
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.removeprefix("sqlite:///")
        if db_path and not db_path.startswith(":"):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / "originals").mkdir(parents=True, exist_ok=True)
    (settings.upload_dir / "annotated").mkdir(parents=True, exist_ok=True)

    # Import so the tables register on Base.metadata before create_all().
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency yielding one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
