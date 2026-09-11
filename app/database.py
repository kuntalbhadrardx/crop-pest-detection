"""SQLAlchemy engine/session setup backed by SQLite."""
import logging
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

logger = logging.getLogger(__name__)


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
    _migrate_sqlite(engine)


def _migrate_sqlite(engine) -> None:
    """Lightweight column additions for DBs created by older versions.

    SQLite's ALTER TABLE ADD COLUMN is cheap, so we patch existing tables
    instead of requiring a throwaway database. New deployments get the
    columns from create_all() and every statement below becomes a no-op.
    """
    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    additions = {
        "scans": [
            ("latitude", "FLOAT"),
            ("longitude", "FLOAT"),
            ("location_name", "VARCHAR(255)"),
            ("crop", "VARCHAR(100)"),
            ("crop_stage", "VARCHAR(50)"),
        ],
    }
    with engine.begin() as conn:
        for table, columns in additions.items():
            if table not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    logger.info("Migrated %s: added column %s", table, name)


def get_db():
    """FastAPI dependency yielding one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
