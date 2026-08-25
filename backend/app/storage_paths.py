from __future__ import annotations

from pathlib import Path

"""Centralizes the legacy (pre-R2) MVP storage path constants.

`main.py`, `routes/detection.py`, and `routes/vlm.py` previously each
computed `BASE_DIR`/`STORAGE_DIR`/etc. independently (identical result,
duplicated logic -- flagged as technical debt H1 in the R2.5 audit). This
is a behavior-preserving extraction only: the directory layout, filenames,
and directory-creation timing (at import time, before the app serves any
request) are all unchanged. No storage migration, no change to what gets
read/written where.

Deliberately NOT merged with `services/storage_service.py` (the *new*,
unrelated Plan-pipeline storage abstraction introduced in R2) or with
`core/config.py`'s `Settings` -- either would broaden this into the
legacy-storage-layout migration the R2.5 audit explicitly deferred to R3
preparation, not a small duplication fix.
"""

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
RENDERED_DIR = STORAGE_DIR / "rendered_pages"
EXPORTS_DIR = STORAGE_DIR / "exports"
HATCH_SAMPLES_DIR = STORAGE_DIR / "hatch_samples"

for _path in (UPLOADS_DIR, RENDERED_DIR, EXPORTS_DIR, HATCH_SAMPLES_DIR):
    _path.mkdir(parents=True, exist_ok=True)
