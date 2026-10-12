from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from ..logging_config import get_logger
from .base import Base

logger = get_logger("db.session")

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def _ensure_data_dir(url: str) -> None:
    """Create data directory for SQLite databases if needed."""
    if url.startswith("sqlite://"):
        db_path = url.replace("sqlite:///", "").replace("sqlite://", "")
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        _ensure_data_dir(url)
        connect_args = {"check_same_thread": False} if "sqlite" in url else {}
        _engine = create_engine(
            url,
            connect_args=connect_args,
            echo=settings.app_env == "development",
        )
        logger.info("Database engine created", extra={"url_type": url.split(":")[0]})
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables. Use Alembic for migrations in production."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("Database tables initialized")
