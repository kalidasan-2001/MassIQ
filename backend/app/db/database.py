from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# pool_pre_ping avoids handing out dead connections after the DB restarts or
# an idle connection is dropped -- cheap correctness win for a long-lived
# engine. future=True is the 2.0-style default going forward; explicit here
# for clarity since the codebase is new to SQLAlchemy.
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session.

    Each request gets its own Session (no global mutable session). Commits
    are the caller's (service layer's) responsibility, not this dependency's
    -- this function only guarantees rollback-on-error and close-on-exit so a
    failed request never leaves a dangling transaction or connection.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
