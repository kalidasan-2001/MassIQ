from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.quantity_result import QuantityResultStatus
from app.schemas.results import ResultRowResponse
from app.services.excel_service import build_results_workbook
from app.services.export_security import sanitize_filename_component
from app.services.project_service import ProjectNotFoundError, ProjectService
from app.services.results_export import build_export_dto, group_totals_by_material
from app.services.results_service import ResultNotFoundError, ResultsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/results", tags=["results"])


def get_results_service(db: Session = Depends(get_db)) -> ResultsService:
    return ResultsService(db)


def get_project_service(db: Session = Depends(get_db)) -> ProjectService:
    return ProjectService(db)


def _not_found(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNotFoundError):
        return HTTPException(status_code=404, detail="Project not found")
    if isinstance(exc, ResultNotFoundError):
        return HTTPException(status_code=404, detail="Quantity result not found")
    return HTTPException(status_code=404, detail="Not found")


@router.get("", response_model=list[ResultRowResponse])
async def list_results(
    project_id: uuid.UUID,
    service: ResultsService = Depends(get_results_service),
) -> list[ResultRowResponse]:
    """Returns every QuantityResult for this project regardless of status
    (R8 section 24: the UI must be able to show DRAFT results too, clearly
    labeled) -- filtering to CONFIRMED-only is the export endpoint's job,
    not this one's."""
    try:
        return service.list_results(project_id)  # type: ignore[return-value]
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post("/export")
async def export_results(
    project_id: uuid.UUID,
    results_service: ResultsService = Depends(get_results_service),
    project_service: ProjectService = Depends(get_project_service),
) -> StreamingResponse:
    """R8 section 8: default export = CONFIRMED quantities only -- a
    DRAFT QuantityResult (by definition not yet reviewed/approved as
    final) never silently appears in a report a user might hand to a
    client or contractor as if it were final."""
    try:
        project = project_service.get_project(project_id)
        rows = results_service.list_results(project_id, status=QuantityResultStatus.CONFIRMED)
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc

    if not rows:
        raise HTTPException(
            status_code=409,
            detail="No confirmed quantities to export yet -- confirm at least one QuantityResult first.",
        )

    start = time.perf_counter()
    dto = build_export_dto(project.name, rows)
    material_totals = group_totals_by_material(rows)
    try:
        workbook_bytes = build_results_workbook(dto, material_totals)
    except Exception:
        # Never a raw openpyxl/IO traceback to the client (R8 section 40).
        logger.exception("results_export_failed project_id=%s row_count=%d", project_id, len(rows))
        raise HTTPException(status_code=500, detail="Failed to generate the export workbook.") from None
    duration_ms = (time.perf_counter() - start) * 1000

    logger.info(
        "results_exported project_id=%s quantity_count=%d confirmed_count=%d duration_ms=%.1f row_count=%d",
        project_id, len(rows), len(rows), duration_ms, len(rows),
    )

    safe_project = sanitize_filename_component(project.name)
    date_stamp = dto.export_timestamp.strftime("%Y%m%d")
    filename = f"MassIQ_{safe_project}_quantities_{date_stamp}.xlsx"

    return StreamingResponse(
        BytesIO(workbook_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/preflight")
async def export_preflight(
    project_id: uuid.UUID,
    project_service: ProjectService = Depends(get_project_service),
    results_service: ResultsService = Depends(get_results_service),
) -> dict:
    """A cheap, side-effect-free check the frontend uses to enable/disable
    the Export button and show an accurate count -- without generating a
    workbook just to find out there is nothing to export."""
    try:
        project_service.get_project(project_id)
        confirmed = results_service.list_results(project_id, status=QuantityResultStatus.CONFIRMED)
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc
    return {"confirmed_count": len(confirmed), "can_export": len(confirmed) > 0}


# Registered AFTER the literal /export and /export/preflight routes above,
# on purpose -- /{quantity_result_id} is a single dynamic path segment at
# the same nesting level, so it must not be given a chance to shadow them.
@router.get("/{quantity_result_id}", response_model=ResultRowResponse)
async def get_result(
    project_id: uuid.UUID,
    quantity_result_id: uuid.UUID,
    service: ResultsService = Depends(get_results_service),
) -> ResultRowResponse:
    try:
        return service.get_result(project_id, quantity_result_id)  # type: ignore[return-value]
    except (ProjectNotFoundError, ResultNotFoundError) as exc:
        raise _not_found(exc) from exc
