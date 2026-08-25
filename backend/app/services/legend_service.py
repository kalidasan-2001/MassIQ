from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.legend_entry import LegendEntry, LegendEntryStatus
from app.models.plan_page import PlanPage
from app.schemas.legend_entry import LegendEntryUpdate
from app.services.legend_crop_service import CropBoundsError, LegendCropService, RegionSelection
from app.services.ocr_service import OcrResult, OcrService
from app.services.plan_service import PlanService
from app.services.storage_service import StorageError, StorageService

logger = logging.getLogger(__name__)

__all__ = [
    "LegendService",
    "LegendEntryNotFoundError",
    "DescriptionNotSelectedError",
    "LegendConfirmationError",
]


class LegendEntryNotFoundError(Exception):
    def __init__(self, legend_entry_id: uuid.UUID):
        self.legend_entry_id = legend_entry_id
        super().__init__(f"LegendEntry {legend_entry_id} not found")


class DescriptionNotSelectedError(Exception):
    """Raised by run_ocr when no description crop has been saved yet --
    OCR has nothing to read. Distinct from LegendEntryNotFoundError so
    routes can return an accurate 400, not a 404."""

    def __init__(self, legend_entry_id: uuid.UUID):
        self.legend_entry_id = legend_entry_id
        super().__init__(f"LegendEntry {legend_entry_id} has no description selection to run OCR on")


class LegendConfirmationError(Exception):
    """Raised by confirm() when required fields are missing. Carries the
    specific reasons so the API response can tell the user what's left,
    rather than a generic 'cannot confirm'."""

    def __init__(self, legend_entry_id: uuid.UUID, reasons: list[str]):
        self.legend_entry_id = legend_entry_id
        self.reasons = reasons
        super().__init__(f"LegendEntry {legend_entry_id} cannot be confirmed: {'; '.join(reasons)}")


class LegendService:
    """Owns LegendEntry domain/application logic: the two-selection
    hatch-pattern + description workflow, OCR, user correction, material
    confirmation. Deliberately does NOT do hatch feature extraction,
    pattern-library matching, or automatic material decisions -- see the
    R3 checklist's explicit out-of-scope list.

    Composes PlanService for every ownership/isolation check (no duplicated
    project/plan/page lookup logic) and StorageService/LegendCropService/
    OcrService for the mechanics. A client never supplies plan_page_id
    directly -- create_draft always resolves it via PlanService.get_page,
    so a created LegendEntry's project_id/plan_id/plan_page_id are
    mutually consistent by construction.
    """

    def __init__(
        self,
        db: Session,
        storage: StorageService | None = None,
        ocr: OcrService | None = None,
    ):
        self._db = db
        self._storage = storage or StorageService()
        self._plan_service = PlanService(db, storage=self._storage)
        self._crop_service = LegendCropService(self._storage)
        self._ocr = ocr or OcrService()

    # -- lookups -----------------------------------------------------

    def _require_entry(self, project_id: uuid.UUID, plan_id: uuid.UUID, legend_entry_id: uuid.UUID) -> LegendEntry:
        # Reuses PlanService.get_plan's existing project/plan ownership and
        # isolation check -- a Plan that exists but belongs to a different
        # project already 404s here, before we even look at the entry.
        self._plan_service.get_plan(project_id, plan_id)
        entry = self._db.get(LegendEntry, legend_entry_id)
        # Cross-plan isolation: an entry that exists but belongs to a
        # different plan must 404, not leak as if it belonged to this one.
        if entry is None or entry.plan_id != plan_id:
            raise LegendEntryNotFoundError(legend_entry_id)
        return entry

    def get_entry(self, project_id: uuid.UUID, plan_id: uuid.UUID, legend_entry_id: uuid.UUID) -> LegendEntry:
        return self._require_entry(project_id, plan_id, legend_entry_id)

    def list_entries(self, project_id: uuid.UUID, plan_id: uuid.UUID) -> list[LegendEntry]:
        self._plan_service.get_plan(project_id, plan_id)
        stmt = (
            select(LegendEntry)
            .where(LegendEntry.plan_id == plan_id)
            .order_by(LegendEntry.created_at.desc())
        )
        return list(self._db.scalars(stmt).all())

    # -- creation and correction --------------------------------------

    def create_draft(self, project_id: uuid.UUID, plan_id: uuid.UUID, page_number: int) -> LegendEntry:
        # Raises ProjectNotFoundError / PlanNotFoundError / PlanPageNotFoundError
        # as appropriate -- the same tested chain every other Plan route uses.
        page = self._plan_service.get_page(project_id, plan_id, page_number)
        entry = LegendEntry(
            project_id=project_id,
            plan_id=plan_id,
            plan_page_id=page.id,
            status=LegendEntryStatus.DRAFT,
        )
        self._db.add(entry)
        self._db.commit()
        self._db.refresh(entry)
        logger.info(
            "legend_entry_created legend_entry_id=%s project_id=%s plan_id=%s plan_page_id=%s",
            entry.id, project_id, plan_id, page.id,
        )
        return entry

    def update_entry(
        self, project_id: uuid.UUID, plan_id: uuid.UUID, legend_entry_id: uuid.UUID, payload: LegendEntryUpdate
    ) -> LegendEntry:
        entry = self._require_entry(project_id, plan_id, legend_entry_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(entry, field, value)
        self._db.commit()
        self._db.refresh(entry)
        logger.info(
            "legend_entry_updated legend_entry_id=%s project_id=%s plan_id=%s fields=%s",
            entry.id, project_id, plan_id, sorted(payload.model_dump(exclude_unset=True).keys()),
        )
        return entry

    # -- selections ----------------------------------------------------

    def _save_selection(
        self, project_id: uuid.UUID, plan_id: uuid.UUID, legend_entry_id: uuid.UUID, kind: str, selection: RegionSelection
    ) -> LegendEntry:
        entry = self._require_entry(project_id, plan_id, legend_entry_id)
        plan_page = self._db.get(PlanPage, entry.plan_page_id)
        # CropBoundsError / StorageError propagate to the caller (route maps
        # them to 400/404) -- nothing is written to disk or the DB if the
        # crop itself fails.
        crop_bytes = self._crop_service.crop_region(plan_page, selection)
        reference = self._storage.save_legend_crop(plan_id, entry.id, kind, crop_bytes)

        setattr(entry, f"{kind}_x", selection.x)
        setattr(entry, f"{kind}_y", selection.y)
        setattr(entry, f"{kind}_width", selection.width)
        setattr(entry, f"{kind}_height", selection.height)
        setattr(entry, f"{kind}_image_reference", reference)
        self._db.commit()
        self._db.refresh(entry)
        logger.info(
            "legend_entry_%s_selection_saved legend_entry_id=%s project_id=%s plan_id=%s plan_page_id=%s",
            kind, entry.id, project_id, plan_id, entry.plan_page_id,
        )
        return entry

    def save_pattern_selection(
        self, project_id: uuid.UUID, plan_id: uuid.UUID, legend_entry_id: uuid.UUID, selection: RegionSelection
    ) -> LegendEntry:
        return self._save_selection(project_id, plan_id, legend_entry_id, "pattern", selection)

    def save_description_selection(
        self, project_id: uuid.UUID, plan_id: uuid.UUID, legend_entry_id: uuid.UUID, selection: RegionSelection
    ) -> LegendEntry:
        return self._save_selection(project_id, plan_id, legend_entry_id, "description", selection)

    def get_crop_path(self, project_id: uuid.UUID, plan_id: uuid.UUID, legend_entry_id: uuid.UUID, kind: str):
        entry = self._require_entry(project_id, plan_id, legend_entry_id)
        reference = getattr(entry, f"{kind}_image_reference")
        if not reference:
            raise StorageError(f"No {kind} crop has been saved for this legend entry yet")
        return self._storage.resolve_legend_crop(reference)

    # -- OCR -------------------------------------------------------------

    def run_ocr(
        self, project_id: uuid.UUID, plan_id: uuid.UUID, legend_entry_id: uuid.UUID
    ) -> tuple[LegendEntry, OcrResult]:
        entry = self._require_entry(project_id, plan_id, legend_entry_id)
        if not entry.description_image_reference:
            raise DescriptionNotSelectedError(legend_entry_id)

        image_path = self._storage.resolve_legend_crop(entry.description_image_reference)
        result = self._ocr.extract_text(image_path)  # never raises -- OCR is assistance, not truth

        # Status always advances to OCR_COMPLETE once the step has been
        # attempted, whether OCR found text, found nothing, or the
        # provider itself failed -- the *how it went* lives in `result`
        # (returned to the caller, not persisted beyond raw_ocr_text),
        # not in the entry's status. This is what makes OCR failure
        # non-fatal: the user can always type the description and continue.
        entry.raw_ocr_text = result.text or None
        entry.status = LegendEntryStatus.OCR_COMPLETE
        self._db.commit()
        self._db.refresh(entry)

        logger.info(
            "legend_entry_ocr_run legend_entry_id=%s project_id=%s plan_id=%s provider=%s success=%s",
            entry.id, project_id, plan_id, result.provider, result.error is None,
        )
        return entry, result

    # -- confirmation ------------------------------------------------

    def confirm(self, project_id: uuid.UUID, plan_id: uuid.UUID, legend_entry_id: uuid.UUID) -> LegendEntry:
        entry = self._require_entry(project_id, plan_id, legend_entry_id)

        reasons = []
        if not entry.pattern_image_reference:
            reasons.append("pattern selection is required")
        if not entry.description_image_reference:
            reasons.append("description selection is required")
        if not (entry.corrected_text or "").strip():
            reasons.append("corrected description text is required")
        if not (entry.material_name or "").strip():
            reasons.append("material name is required")
        if reasons:
            raise LegendConfirmationError(legend_entry_id, reasons)

        entry.status = LegendEntryStatus.CONFIRMED
        entry.confirmed_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(entry)
        logger.info(
            "legend_entry_confirmed legend_entry_id=%s project_id=%s plan_id=%s",
            entry.id, project_id, plan_id,
        )
        return entry
