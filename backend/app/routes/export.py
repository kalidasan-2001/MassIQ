from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.excel_service import build_excel_report

router = APIRouter(tags=["export"])


class ExportPayload(BaseModel):
    project_name: str
    plan_name: str | None = None
    component: str
    detection_method: str | None = None
    hatch_sample_used: bool | None = True
    total_detections: int | None = 0
    accepted_detections: int | None = 0
    rejected_detections: int | None = 0
    pending_detections: int | None = 0
    manual_add_count: int | None = 0
    manual_subtract_count: int | None = 0
    area_m2: float
    accepted_detection_area_m2: float | None = 0
    added_correction_area_m2: float | None = 0
    subtracted_correction_area_m2: float | None = 0
    height_m: float
    volume_m3: float
    notes: str | None = None
    review_status: str | None = None


@router.post("/export-excel")
async def export_excel(payload: ExportPayload):
    data = build_excel_report(payload.model_dump())
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="massiq_quantity_report.xlsx"'},
    )
