from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.routes import detection, export, vlm
from app.services.measurement_service import analyze_section_dimensions
from app.services.pdf_service import convert_pdf_first_page_to_png, suggest_plan_scale

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
RENDERED_DIR = STORAGE_DIR / "rendered_pages"
EXPORTS_DIR = STORAGE_DIR / "exports"
HATCH_SAMPLES_DIR = STORAGE_DIR / "hatch_samples"

for path in (UPLOADS_DIR, RENDERED_DIR, EXPORTS_DIR, HATCH_SAMPLES_DIR):
    path.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="MassIQ MVP Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(export.router)
app.include_router(detection.router)
app.include_router(vlm.router)


@app.get("/")
async def root():
    return {"status": "ok", "message": "MassIQ backend running"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")
    file_id = uuid.uuid4().hex
    pdf_path = UPLOADS_DIR / f"{file_id}.pdf"
    pdf_path.write_bytes(await file.read())
    image_path = RENDERED_DIR / f"{file_id}.png"
    metadata = convert_pdf_first_page_to_png(pdf_path, image_path)
    return {
        "file_id": file_id,
        "page_image_url": f"/rendered-page/{file_id}",
        "width": metadata["width"],
        "height": metadata["height"],
    }


@app.get("/rendered-page/{file_id}")
async def rendered_page(file_id: str):
    image_path = RENDERED_DIR / f"{file_id}.png"
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Rendered page not found")
    return FileResponse(image_path)


@app.post("/suggest-plan-scale/{file_id}")
async def plan_scale(file_id: str):
    image_path = RENDERED_DIR / f"{file_id}.png"
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Rendered page not found")
    return suggest_plan_scale(image_path)


@app.post("/analyze-section/{section_file_id}")
async def section_analysis(section_file_id: str):
    image_path = RENDERED_DIR / f"section_{section_file_id}.png"
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Rendered section not found")
    return analyze_section_dimensions(image_path)
