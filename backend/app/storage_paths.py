from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings

"""Centralizes the legacy (pre-R2) MVP storage path constants.

`main.py`, `routes/detection.py`, and `routes/vlm.py` previously each
computed `BASE_DIR`/`STORAGE_DIR`/etc. independently (identical result,
duplicated logic -- flagged as technical debt H1 in the R2.5 audit). This
is a behavior-preserving extraction only: the directory layout, filenames,
and directory-creation timing (at import time, before the app serves any
request) are all unchanged. No storage migration, no change to what gets
read/written where.

R3.5: now reads `Settings.storage_root` (the `STORAGE_ROOT` env var) when
set -- the exact override `core/config.py` already documented as intended
for "the storage root used by main.py's upload/render pipeline" but never
wired up. This lets an isolated E2E (or any other) run point the entire
legacy storage tree at a throwaway directory instead of writing into a
developer's real `backend/app/storage/`. Unset (the default) preserves
today's behavior exactly. Mirrors exactly how `StorageService` already
interprets the same setting for the new Plan pipeline, so both trees land
under the same override root when one is configured, with no name
collision (`plans/` vs `uploads/`/`rendered_pages/`/etc.).

Deliberately NOT merged with `services/storage_service.py` (the *new*,
unrelated Plan-pipeline storage abstraction introduced in R2) -- that
would broaden this into the legacy-storage-layout migration the R2.5
audit explicitly deferred to R3 preparation, not a small duplication fix.
"""

_settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = Path(_settings.storage_root).resolve() if _settings.storage_root else (BASE_DIR / "storage")
UPLOADS_DIR = STORAGE_DIR / "uploads"
RENDERED_DIR = STORAGE_DIR / "rendered_pages"
EXPORTS_DIR = STORAGE_DIR / "exports"
HATCH_SAMPLES_DIR = STORAGE_DIR / "hatch_samples"

for _path in (UPLOADS_DIR, RENDERED_DIR, EXPORTS_DIR, HATCH_SAMPLES_DIR):
    _path.mkdir(parents=True, exist_ok=True)
