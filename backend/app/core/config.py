from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Same directory main.py's storage constants are computed relative to. Not
# used to change existing storage behavior in R1 -- exposed only so future
# services can read it from one place instead of recomputing it.
_APP_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Centralized application configuration.

    Values are read from environment variables (case-insensitive) with an
    optional `.env` file as a fallback, matching the `load_dotenv()` behavior
    `main.py` already relies on. Existing env var names (`OPENAI_API_KEY`,
    `OPENAI_VLM_MODEL`) are preserved unchanged so `vlm_service.py`'s direct
    `os.getenv(...)` calls keep working exactly as before; Settings exposes
    the same variables for new code that wants a typed, testable source
    instead of ad hoc `os.getenv`.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Required for any DB-backed feature (R1+). No production default on
    # purpose -- Rule: do not silently fall back to SQLite in production.
    # The local default below points at the docker-compose Postgres service
    # documented in docs/releases/R1_PROJECT_PERSISTENCE_CHECKLIST.md and is
    # meant for first-run local dev convenience only, not a hidden prod path.
    # Host port 5433 (not the Postgres-standard 5432) because this dev
    # machine already runs an unrelated project's Postgres container on 5432.
    database_url: str = "postgresql+psycopg2://massiq:massiq@127.0.0.1:5433/massiq"

    # Optional override for the storage root used by main.py's upload/render
    # pipeline. None preserves today's behavior exactly (each module keeps
    # computing its own path under backend/app/storage). Not wired into
    # existing storage code in R1 -- reserved for the future StorageService.
    storage_root: str | None = None

    openai_api_key: str | None = None
    openai_vlm_model: str = "gpt-4.1-mini"

    # R2 -- Plan/PDF ingestion pipeline render settings. Explicit and
    # centralized per the R2 instructions ("do not use hidden DPI constants
    # scattered across files"). 144 DPI matches the old MVP's hardcoded
    # fitz.Matrix(2, 2) (2x zoom == 144 DPI, since PyMuPDF's zoom baseline is
    # 72 DPI) so the new pipeline's default visual quality is unchanged from
    # today's behavior -- it is a new, independent setting, not a read of the
    # old pdf_service.convert_pdf_first_page_to_png's hardcoded values, which
    # remain untouched for the old /upload-pdf workflow.
    plan_render_dpi: int = 144
    plan_render_max_width: int = 1800


@lru_cache
def get_settings() -> Settings:
    return Settings()
