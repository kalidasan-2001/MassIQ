"""R8 scope: a read-only Results domain over R7's authoritative
QuantityResult rows (R8 section 5). Deliberately does NOT introduce a new
persisted table -- every field a result row needs already exists on
QuantityResult/DetectionRun/LegendEntry/PatternLibraryEntry/Plan/PlanPage
(R8 section 46: "do not create a table just because every previous
release had one").

Material provenance is resolved through the SAME chain R6/R7 already
established (QuantityResult -> DetectionRun -> reference LegendEntry OR
PatternLibraryEntry -> confirmed material) -- never re-inferred, never a
fresh R5 similarity computation (R8 section 7).

N+1 avoidance (R8 section 44): `list_results` batch-fetches every
referenced DetectionRun/Plan/PlanPage/LegendEntry/PatternLibraryEntry/
rejected-region-count in a small constant number of queries, regardless
of how many QuantityResult rows are being listed -- not a relationship()
eager-load (this codebase's established precedent since R1 is
unidirectional FKs with no relationship/back_populates added to a model
by a later release), but a plain batched IN(...) fetch per referenced
table.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.detected_region import DetectedRegion, DetectedRegionStatus
from app.models.detection_run import DetectionRun
from app.models.legend_entry import LegendEntry
from app.models.pattern_library_entry import PatternLibraryEntry
from app.models.plan import Plan
from app.models.plan_page import PlanPage
from app.models.plan_scale import PlanScale
from app.models.quantity_result import QuantityResult, QuantityResultStatus
from app.services.project_service import ProjectService

__all__ = ["ResultsService", "ResultRow", "ResultNotFoundError"]


class ResultNotFoundError(Exception):
    def __init__(self, quantity_result_id: uuid.UUID):
        self.quantity_result_id = quantity_result_id
        super().__init__(f"QuantityResult {quantity_result_id} not found")


@dataclass(frozen=True)
class ResultRow:
    """The export/display DTO for one authoritative QuantityResult (R8
    section 6). Deliberately exposes no internal filesystem path anywhere
    -- only IDs, names, numbers, and status."""

    quantity_result_id: uuid.UUID
    project_id: uuid.UUID
    plan_id: uuid.UUID
    plan_name: str
    plan_page_id: uuid.UUID
    page_number: int
    material_name: str
    material_code: str | None
    area_m2: float
    confirmed_dimension_m: float
    volume_m3: float
    status: QuantityResultStatus
    calculation_version: str
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None
    detection_run_id: uuid.UUID
    reference_type: str  # "legend_entry" | "pattern_library_entry"
    reference_id: uuid.UUID
    accepted_region_count: int
    rejected_region_count: int
    manual_add_count: int
    manual_subtract_count: int
    scale_method: str | None


class ResultsService:
    def __init__(self, db: Session):
        self._db = db
        self._project_service = ProjectService(db)

    def list_results(
        self, project_id: uuid.UUID, status: QuantityResultStatus | None = None
    ) -> list[ResultRow]:
        self._project_service.get_project(project_id)  # existence/ownership check

        query = self._db.query(QuantityResult).filter(QuantityResult.project_id == project_id)
        if status is not None:
            query = query.filter(QuantityResult.status == status)
        results = query.all()
        rows = self._to_rows(results)

        # Deterministic ordering (R8 section 10): plan -> page -> material
        # -> QuantityResult ID as a final, always-unique tie-breaker, so
        # repeated exports of unchanged data always produce the same row
        # order.
        rows.sort(key=lambda r: (r.plan_name, r.page_number, r.material_name, str(r.quantity_result_id)))
        return rows

    def get_result(self, project_id: uuid.UUID, quantity_result_id: uuid.UUID) -> ResultRow:
        self._project_service.get_project(project_id)
        result = self._db.get(QuantityResult, quantity_result_id)
        if result is None or result.project_id != project_id:
            raise ResultNotFoundError(quantity_result_id)
        return self._to_rows([result])[0]

    def _to_rows(self, results: list[QuantityResult]) -> list[ResultRow]:
        if not results:
            return []

        run_ids = {r.detection_run_id for r in results}
        plan_ids = {r.plan_id for r in results}
        page_ids = {r.plan_page_id for r in results}

        runs = {
            run.id: run
            for run in self._db.query(DetectionRun).filter(DetectionRun.id.in_(run_ids)).all()
        }
        plans = {plan.id: plan for plan in self._db.query(Plan).filter(Plan.id.in_(plan_ids)).all()}
        pages = {
            page.id: page for page in self._db.query(PlanPage).filter(PlanPage.id.in_(page_ids)).all()
        }

        legend_entry_ids = {
            run.reference_legend_entry_id for run in runs.values() if run.reference_legend_entry_id is not None
        }
        library_entry_ids = {
            run.reference_pattern_library_entry_id
            for run in runs.values()
            if run.reference_pattern_library_entry_id is not None
        }
        legend_entries = (
            {
                e.id: e
                for e in self._db.query(LegendEntry).filter(LegendEntry.id.in_(legend_entry_ids)).all()
            }
            if legend_entry_ids
            else {}
        )
        library_entries = (
            {
                e.id: e
                for e in self._db.query(PatternLibraryEntry)
                .filter(PatternLibraryEntry.id.in_(library_entry_ids))
                .all()
            }
            if library_entry_ids
            else {}
        )

        scales = (
            {
                s.plan_page_id: s
                for s in self._db.query(PlanScale).filter(PlanScale.plan_page_id.in_(page_ids)).all()
            }
            if page_ids
            else {}
        )

        # One GROUP BY query for every run's rejected-region count, instead
        # of one COUNT(*) query per result row.
        rejected_counts = dict(
            self._db.query(DetectedRegion.detection_run_id, func.count(DetectedRegion.id))
            .filter(
                DetectedRegion.detection_run_id.in_(run_ids),
                DetectedRegion.status == DetectedRegionStatus.REJECTED,
            )
            .group_by(DetectedRegion.detection_run_id)
            .all()
        )

        rows = []
        for result in results:
            run = runs[result.detection_run_id]
            plan = plans[result.plan_id]
            page = pages[result.plan_page_id]

            if run.reference_legend_entry_id is not None:
                reference_type = "legend_entry"
                reference_id = run.reference_legend_entry_id
                entry = legend_entries.get(reference_id)
                material_name = entry.material_name if entry and entry.material_name else "Unknown material"
                material_code = entry.material_code if entry else None
            else:
                reference_type = "pattern_library_entry"
                reference_id = run.reference_pattern_library_entry_id
                entry = library_entries.get(reference_id)
                material_name = entry.canonical_material_name if entry else "Unknown material"
                material_code = entry.material_code if entry else None

            rows.append(
                ResultRow(
                    quantity_result_id=result.id,
                    project_id=result.project_id,
                    plan_id=result.plan_id,
                    plan_name=plan.original_filename,
                    plan_page_id=result.plan_page_id,
                    page_number=page.page_number,
                    material_name=material_name,
                    material_code=material_code,
                    area_m2=result.final_area_m2,
                    confirmed_dimension_m=result.confirmed_dimension_m,
                    volume_m3=result.volume_m3,
                    status=result.status,
                    calculation_version=result.calculation_version,
                    created_at=result.created_at,
                    updated_at=result.updated_at,
                    confirmed_at=result.confirmed_at,
                    detection_run_id=result.detection_run_id,
                    reference_type=reference_type,
                    reference_id=reference_id,
                    accepted_region_count=result.accepted_region_count,
                    rejected_region_count=rejected_counts.get(result.detection_run_id, 0),
                    manual_add_count=result.manual_add_count,
                    manual_subtract_count=result.manual_subtract_count,
                    scale_method=scales[page.id].method.value if page.id in scales else None,
                )
            )
        return rows
