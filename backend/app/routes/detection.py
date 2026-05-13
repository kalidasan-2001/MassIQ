from __future__ import annotations

from pathlib import Path
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from PIL import Image

from app.services.hatch_detection import detect_hatch_regions

router = APIRouter(tags=["detection"])
BASE_DIR = Path(__file__).resolve().parents[1]
STORAGE_DIR = BASE_DIR / "storage"
RENDERED_DIR = STORAGE_DIR / "rendered_pages"
HATCH_SAMPLES_DIR = STORAGE_DIR / "hatch_samples"


class DetectionRequest(BaseModel):
    file_id: str
    hatch_sample_id: str
    threshold: float = 0.7
    min_region_size: int = 225
    merge_nearby_detections: bool = True
    remove_small_noise: bool = True


class HatchSampleRequest(BaseModel):
    file_id: str
    x: int | None = None
    y: int | None = None
    w: int | None = None
    h: int | None = None
    bbox: dict | None = None
    component_name: str = "Stahlbeton C25/30"


@router.post("/save-hatch-sample")
async def save_hatch_sample(payload: HatchSampleRequest):
    page_image = RENDERED_DIR / f"{payload.file_id}.png"
    if not page_image.exists():
        raise HTTPException(status_code=404, detail="Rendered page image not found")

    if payload.bbox:
        raw_x = payload.bbox.get("x")
        raw_y = payload.bbox.get("y")
        raw_w = payload.bbox.get("width")
        raw_h = payload.bbox.get("height")
    else:
        raw_x = payload.x
        raw_y = payload.y
        raw_w = payload.w
        raw_h = payload.h

    if raw_x is None or raw_y is None or raw_w is None or raw_h is None:
        raise HTTPException(status_code=400, detail="Hatch sample coordinates are required")

    x = max(0, int(raw_x))
    y = max(0, int(raw_y))
    w = max(1, int(raw_w))
    h = max(1, int(raw_h))

    with Image.open(page_image) as image:
        right = min(image.width, x + w)
        bottom = min(image.height, y + h)
        if right <= x or bottom <= y:
            raise HTTPException(status_code=400, detail="Invalid hatch sample bounds")
        crop = image.crop((x, y, right, bottom))
        if crop.width < 4 or crop.height < 4:
            raise HTTPException(status_code=400, detail="Hatch sample selection is too small")
        hatch_sample_id = uuid.uuid4().hex
        hatch_sample_path = HATCH_SAMPLES_DIR / f"{hatch_sample_id}.png"
        crop.save(hatch_sample_path, format="PNG")

    return {
        "hatch_sample_id": hatch_sample_id,
        "component_name": payload.component_name,
        "width": crop.width,
        "height": crop.height,
    }


@router.post("/detect-hatch")
async def detect_hatch(payload: DetectionRequest):
    page_image = RENDERED_DIR / f"{payload.file_id}.png"
    hatch_sample = HATCH_SAMPLES_DIR / f"{payload.hatch_sample_id}.png"
    if not page_image.exists():
        raise HTTPException(status_code=404, detail="Rendered page image not found")
    if not hatch_sample.exists():
        raise HTTPException(status_code=404, detail="Hatch sample not found")
    detections = detect_hatch_regions(
        page_image,
        hatch_sample,
        threshold=payload.threshold,
        min_region_size=payload.min_region_size,
        merge_nearby_detections=payload.merge_nearby_detections,
        remove_small_noise=payload.remove_small_noise,
    )
    return {"detections": detections, "count": len(detections)}
