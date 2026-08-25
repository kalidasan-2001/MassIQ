"""Shared helpers for R1 integration tests. Not a test module itself (name
doesn't match the `test_*.py` discovery pattern).

Deliberately targets a *separate* Postgres database (`massiq_test` by
default) derived from the app's own DATABASE_URL, so running the test suite
never reads or writes a developer's real `massiq` database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402


def test_database_url() -> str:
    override = os.getenv("TEST_DATABASE_URL")
    if override:
        return override
    url = sa.engine.make_url(get_settings().database_url)
    # render_as_string(hide_password=False), NOT str()/plain render_as_string():
    # both of those mask the password as a literal "***", which then fails
    # authentication once this string is re-parsed by make_url() elsewhere.
    return url.set(database="massiq_test").render_as_string(hide_password=False)


def ensure_database_exists(url: str) -> None:
    target = sa.engine.make_url(url)
    admin_engine = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target.database},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        admin_engine.dispose()


def migrate_to_head(url: str) -> None:
    # alembic/env.py resolves its DB URL from ALEMBIC_DATABASE_URL (falling
    # back to the app's own Settings) rather than from Config's sqlalchemy.url
    # -- setting sqlalchemy.url directly here would be silently ignored and
    # migrate the *dev* database instead of this test database.
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    previous = os.environ.get("ALEMBIC_DATABASE_URL")
    os.environ["ALEMBIC_DATABASE_URL"] = url
    try:
        command.upgrade(alembic_cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL"] = previous


def build_test_engine() -> Engine:
    url = test_database_url()
    ensure_database_exists(url)
    migrate_to_head(url)
    return create_engine(url, future=True)


def new_sessionmaker(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, future=True, autoflush=False, autocommit=False)


def truncate_projects(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE projects RESTART IDENTITY CASCADE"))


# R2: same statement as truncate_projects, given its own name because
# TRUNCATE ... CASCADE on `projects` also truncates every table with a (direct
# or transitive) FK back to it -- `plans` (project_id -> projects.id) and, in
# turn, `plan_pages` (plan_id -> plans.id). Kept as a separate function so R2
# test files read as "clear everything" rather than "clear projects" only.
truncate_all = truncate_projects
