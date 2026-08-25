from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from app.core.config import get_settings


class StorageError(RuntimeError):
    pass


class StorageService:
    """Owns all filesystem path construction for the R2 Plan pipeline.

    Persisted DB references (`Plan.stored_file_reference`,
    `PlanPage.preview_reference`) are always storage-root-relative,
    forward-slash strings such as "plans/<plan_uuid>/original.pdf" -- never
    absolute machine paths. This keeps them portable across machines/
    environments and resolvable purely from `Settings.storage_root` (or the
    default `backend/app/storage/`) at read time.

    Every path segment this service builds is server-generated: `plan_id` is
    a UUID minted by PlanService, `page_number` is an int PdfInspectionService
    derives from the document itself. The client-supplied original filename
    is stored only as `Plan.original_filename` metadata and is never passed
    into any path-construction method here -- so there is no client input in
    any path this service builds, which is the real defense against path
    traversal. `_safe_path` re-validates every resolved path stays under the
    storage root regardless, as a second, defensive layer.

    This is intentionally separate from the old MVP's `UPLOADS_DIR` /
    `RENDERED_DIR` / `HATCH_SAMPLES_DIR` constants in main.py and
    routes/detection.py, which are left untouched -- see the R2 checklist's
    "temporary duplication" note.
    """

    def __init__(self, root: Path | None = None):
        settings = get_settings()
        configured_root = root or (Path(settings.storage_root) if settings.storage_root else None)
        self.root = (configured_root or (Path(__file__).resolve().parents[1] / "storage")).resolve()
        self.plans_root = self.root / "plans"
        self.plans_root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, relative: str) -> Path:
        candidate = (self.root / relative).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            raise StorageError(f"Path escapes storage root: {relative!r}") from None
        return candidate

    def _plan_dir(self, plan_id: uuid.UUID) -> Path:
        return self.plans_root / str(plan_id)

    def save_original_plan(self, plan_id: uuid.UUID, content: bytes) -> str:
        plan_dir = self._plan_dir(plan_id)
        plan_dir.mkdir(parents=True, exist_ok=True)
        target = plan_dir / "original.pdf"
        target.write_bytes(content)
        relative = f"plans/{plan_id}/original.pdf"
        self._safe_path(relative)  # defensive re-validation of the reference we're about to persist
        return relative

    def resolve_original_plan(self, reference: str) -> Path:
        path = self._safe_path(reference)
        if not path.exists():
            raise StorageError(f"Stored file not found: {reference!r}")
        return path

    def save_page_preview(self, plan_id: uuid.UUID, page_number: int, content: bytes) -> str:
        pages_dir = self._plan_dir(plan_id) / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{page_number:04d}.png"
        target = pages_dir / filename
        target.write_bytes(content)
        relative = f"plans/{plan_id}/pages/{filename}"
        self._safe_path(relative)
        return relative

    def resolve_preview(self, reference: str) -> Path:
        path = self._safe_path(reference)
        if not path.exists():
            raise StorageError(f"Stored preview not found: {reference!r}")
        return path

    def delete_plan_assets(self, plan_id: uuid.UUID) -> None:
        """Best-effort cleanup after a failed ingestion. Never raises --
        a cleanup failure must not mask the original ingestion error that
        triggered it (PlanService calls this from an `except` block)."""
        plan_dir = self._plan_dir(plan_id)
        if plan_dir.exists():
            shutil.rmtree(plan_dir, ignore_errors=True)
