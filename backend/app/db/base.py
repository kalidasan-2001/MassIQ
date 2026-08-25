from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models.

    Alembic's env.py imports `Base.metadata` as the autogenerate target, so
    every model module must be imported somewhere before that metadata is
    read (see alembic/env.py's explicit model imports).
    """
