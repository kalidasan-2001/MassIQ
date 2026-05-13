from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.vlm_service import analyze_floor_plan_with_vlm, analyze_section_with_vlm

router = APIRouter(prefix="/vlm", tags=["vlm"])
BASE_DIR = Path(__file__).resolve().parents[1]
RENDERED_DIR = BASE_DIR / "storage" / "rendered_pages"


class FloorPlanRequest(BaseModel):
    file_id: str


class SectionRequest(BaseModel):
    section_file_id: str
    component_name: str = "Stahlbeton C25/30"


@router.post("/analyze-floor-plan")
async def analyze_floor_plan(payload: FloorPlanRequest):
    image_path = RENDERED_DIR / f"{payload.file_id}.png"
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Rendered floor plan image not found")
    return analyze_floor_plan_with_vlm(str(image_path))


@router.post("/analyze-section-view")
async def analyze_section_view(payload: SectionRequest):
    image_path = RENDERED_DIR / f"section_{payload.section_file_id}.png"
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Rendered section image not found")
    return analyze_section_with_vlm(str(image_path), payload.component_name)
