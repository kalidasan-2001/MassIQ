"""Starts a FastAPI backend instance for Playwright E2E testing, pointed at
a fully isolated database and storage root -- E2E runs never touch a
developer's normal `massiq` database or `backend/app/storage/` tree.

The E2E database (`massiq_e2e` by default) is DROPPED and recreated fresh
on every invocation of this script, then migrated to head. This is
deliberate: it is the simplest way to guarantee "tests must be rerunnable"
and "avoid test ordering dependencies" (R3.5 requirements) without needing
per-test cleanup logic -- every full E2E run starts from a genuinely empty,
freshly-migrated schema and an empty storage directory. Individual tests
within one run only need to avoid colliding with *each other* (achieved by
each test creating its own uniquely-named Project through the UI).

Usage (invoked by frontend/e2e/scripts/start-backend.js, not run directly
in normal development):
    python scripts/e2e_server.py --port 8020

Env var overrides (optional):
    MASSIQ_E2E_DATABASE_URL   -- full override; default derives from the
                                  dev DATABASE_URL with the database name
                                  swapped to "massiq_e2e"
    MASSIQ_E2E_STORAGE_ROOT   -- default: a fresh tempfile.mkdtemp() dir,
                                  printed to stdout for the caller's benefit
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402


def _recreate_database(url: str) -> None:
    """Drops (if present) and recreates the target database. Connects to
    the server's default `postgres` maintenance database to do so, exactly
    like tests/db_test_support.py's ensure_database_exists, but dropping
    first for a guaranteed-clean E2E run rather than reusing whatever a
    prior run left behind."""
    target = sa.engine.make_url(url)
    admin_engine = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": target.database},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{target.database}"'))
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        admin_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    database_url = os.environ.get("MASSIQ_E2E_DATABASE_URL")
    if not database_url:
        # Deliberately reads the raw DATABASE_URL env var here instead of
        # calling app.core.config.get_settings() -- get_settings() is
        # process-wide @lru_cache'd, and this whole function's job is to
        # compute a *different* DATABASE_URL and set it in os.environ
        # before any app.* module is first imported (see below). Calling
        # get_settings() even once here would permanently cache a Settings
        # instance built from the *original* (dev) DATABASE_URL, and every
        # later app.* import in this same process -- including uvicorn
        # actually serving requests -- would silently keep using that
        # stale, wrong (non-"massiq_e2e") database for the rest of the
        # process's life. This exact bug shipped once already: it was
        # masked for a long time by Playwright's reuseExistingServer
        # reusing one already-correctly-started process across many local
        # runs, and only surfaced when a genuinely fresh, CI-equivalent
        # cold start (CI=true, no reuse) was tested.
        raw_database_url = os.environ.get(
            "DATABASE_URL", "postgresql+psycopg2://massiq:massiq@127.0.0.1:5433/massiq"
        )
        dev_url = sa.engine.make_url(raw_database_url)
        database_url = dev_url.set(database="massiq_e2e").render_as_string(hide_password=False)

    storage_root = os.environ.get("MASSIQ_E2E_STORAGE_ROOT") or tempfile.mkdtemp(prefix="massiq_e2e_storage_")

    print(f"[e2e_server] DATABASE_URL={database_url}", flush=True)
    print(f"[e2e_server] STORAGE_ROOT={storage_root}", flush=True)

    # Must be set before any `app.*` module is imported anywhere in this
    # process, since Settings() is cached (functools.lru_cache) on first
    # call -- this script is a fresh process per E2E run, so that's exactly
    # what happens here.
    os.environ["DATABASE_URL"] = database_url
    os.environ["STORAGE_ROOT"] = storage_root
    os.environ["ALEMBIC_DATABASE_URL"] = database_url

    _recreate_database(database_url)

    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")
    print("[e2e_server] migrations applied, starting uvicorn...", flush=True)

    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
