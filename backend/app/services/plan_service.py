from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.plan import Plan, PlanProcessingStatus
from app.models.plan_page import PlanPage
from app.models.project import Project
from app.services.pdf_inspection_service import (
    InvalidPdfError,
    classify_document,
    inspect_document,
    open_and_validate,
)
from app.services.pdf_service import render_page_to_png_bytes
from app.services.project_service import ProjectNotFoundError
from app.services.storage_service import StorageService

__all__ = ["PlanService", "PlanNotFoundError", "PlanPageNotFoundError", "InvalidPdfError"]


class PlanNotFoundError(Exception):
    def __init__(self, plan_id: uuid.UUID):
        self.plan_id = plan_id
        super().__init__(f"Plan {plan_id} not found")


class PlanPageNotFoundError(Exception):
    """R2.5: raised by get_page when project/plan exist but no PlanPage row
    has the requested page_number -- distinct from PlanNotFoundError so
    routes can 404 with an accurate message."""

    def __init__(self, plan_id: uuid.UUID, page_number: int):
        self.plan_id = plan_id
        self.page_number = page_number
        super().__init__(f"Page {page_number} not found for plan {plan_id}")


class PlanService:
    """Owns Plan/PlanPage domain and application logic, including the PDF
    ingestion pipeline. Deliberately does NOT perform hatch recognition,
    legend extraction, OCR, material recognition, quantity calculation, or
    Excel export -- those remain out of R2's scope entirely.

    Transactional safety strategy (see upload_plan): validation happens
    against the in-memory PDF stream before any DB row or file is written,
    so a rejected upload leaves zero trace. Once a Plan row exists, it stays
    uncommitted (via a single session, no intermediate commits) until every
    PlanPage row and its preview file has been created; any exception in
    between triggers a full DB rollback plus best-effort filesystem cleanup
    of whatever was written for that plan_id, so a Plan can never be
    observed in a state where the DB says READY but pages/previews are
    missing, or where files exist on disk with no corresponding DB row.
    """

    def __init__(self, db: Session, storage: StorageService | None = None):
        self._db = db
        self._storage = storage or StorageService()
        self._settings = get_settings()

    def _require_project(self, project_id: uuid.UUID) -> Project:
        project = self._db.get(Project, project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        return project

    def upload_plan(self, project_id: uuid.UUID, original_filename: str, content: bytes) -> Plan:
        self._require_project(project_id)

        # Validate against the in-memory stream BEFORE creating any DB row
        # or writing any file -- an invalid PDF must leave zero trace.
        doc = open_and_validate(content)  # raises InvalidPdfError; nothing persisted yet

        plan_id = uuid.uuid4()
        try:
            inspections = inspect_document(doc)
            pdf_type = classify_document(inspections)

            stored_reference = self._storage.save_original_plan(plan_id, content)

            plan = Plan(
                id=plan_id,
                project_id=project_id,
                original_filename=original_filename,
                stored_file_reference=stored_reference,
                page_count=doc.page_count,
                processing_status=PlanProcessingStatus.INSPECTING,
                pdf_type=pdf_type,
            )
            self._db.add(plan)
            self._db.flush()  # assigns nothing new (id is client-side), but surfaces FK/constraint errors early

            for inspection in inspections:
                preview_bytes = render_page_to_png_bytes(
                    doc,
                    inspection.page_number - 1,  # PlanPage is 1-based; PyMuPDF/render is 0-based
                    dpi=self._settings.plan_render_dpi,
                    max_width=self._settings.plan_render_max_width,
                )
                preview_reference = self._storage.save_page_preview(plan_id, inspection.page_number, preview_bytes)
                self._db.add(
                    PlanPage(
                        plan_id=plan_id,
                        page_number=inspection.page_number,
                        width=inspection.width,
                        height=inspection.height,
                        rotation=inspection.rotation,
                        vector_content_available=inspection.has_vector_drawings,
                        preview_reference=preview_reference,
                    )
                )

            # Only reachable once every page + preview above succeeded.
            plan.processing_status = PlanProcessingStatus.READY
            self._db.commit()
            self._db.refresh(plan)
            return plan
        except Exception:
            self._db.rollback()
            # Best-effort: remove any files written for this plan_id so a
            # failed ingestion never leaves orphaned original.pdf/preview
            # files with no corresponding (rolled-back) DB row.
            self._storage.delete_plan_assets(plan_id)
            raise
        finally:
            doc.close()

    def list_plans(self, project_id: uuid.UUID) -> list[Plan]:
        self._require_project(project_id)
        stmt = select(Plan).where(Plan.project_id == project_id).order_by(Plan.created_at.desc())
        return list(self._db.scalars(stmt).all())

    def get_plan(self, project_id: uuid.UUID, plan_id: uuid.UUID) -> Plan:
        self._require_project(project_id)
        plan = self._db.get(Plan, plan_id)
        # Project isolation: a Plan that exists but belongs to a different
        # project must 404, not leak as if it belonged to this project_id.
        if plan is None or plan.project_id != project_id:
            raise PlanNotFoundError(plan_id)
        return plan

    def get_page(self, project_id: uuid.UUID, plan_id: uuid.UUID, page_number: int) -> PlanPage:
        """R2.5: the smallest prerequisite the new Plan pipeline needs before
        R3 can show a persisted Plan's page on screen. Reuses get_plan for
        the Project/Plan relationship and project-isolation check -- no
        separate ownership-verification logic."""
        plan = self.get_plan(project_id, plan_id)
        for page in plan.pages:
            if page.page_number == page_number:
                return page
        raise PlanPageNotFoundError(plan_id, page_number)
