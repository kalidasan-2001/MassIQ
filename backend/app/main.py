from __future__ import annotations

import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

load_dotenv()

from app.routes import (
    detection,
    detection_runs,
    export,
    hatch_features,
    legend_entries,
    manual_corrections,
    pattern_library,
    pattern_matches,
    plan_scale,
    plans,
    projects,
    quantity,
    results,
    vlm,
)
from app.services.measurement_service import analyze_section_dimensions
from app.services.pdf_inspection_service import InvalidPdfError, open_and_validate
from app.services.pdf_service import convert_pdf_first_page_to_png, suggest_plan_scale
from app.storage_paths import EXPORTS_DIR, HATCH_SAMPLES_DIR, RENDERED_DIR, STORAGE_DIR, UPLOADS_DIR  # noqa: F401

app = FastAPI(title="MassIQ MVP Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # R8: Content-Disposition is not on the CORS-safelisted response
    # header list, so without this, frontend JS on a different origin/port
    # (true for local dev and the E2E harness -- frontend and backend run
    # on different ports) cannot read the server-chosen, sanitized export
    # filename at all -- found via a real cross-origin browser download in
    # E2E-08, not visible to any same-process pytest/TestClient call.
    expose_headers=["Content-Disposition"],
)
app.include_router(export.router)
app.include_router(detection.router)
app.include_router(vlm.router)
app.include_router(projects.router)
app.include_router(plans.router)
app.include_router(legend_entries.router)
app.include_router(hatch_features.router)
app.include_router(pattern_library.router)
app.include_router(pattern_matches.router)
app.include_router(detection_runs.page_router)
app.include_router(detection_runs.run_router)
app.include_router(plan_scale.router)
app.include_router(manual_corrections.router)
app.include_router(quantity.router)
app.include_router(results.router)


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
    content = await file.read()

    # R2.5 hardening: reuse PdfInspectionService's already-tested validation
    # (magic-byte check + PyMuPDF open + page-0 readability) instead of a
    # second validation implementation. Runs against the in-memory bytes
    # BEFORE anything is written to disk, so a corrupt/empty/fake-PDF upload
    # is rejected with a clean 4xx and leaves zero trace -- no partial
    # uploads/*.pdf or rendered_pages/*.png file for a failed upload.
    try:
        validation_doc = open_and_validate(content)
    except InvalidPdfError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    validation_doc.close()

    file_id = uuid.uuid4().hex
    pdf_path = UPLOADS_DIR / f"{file_id}.pdf"
    pdf_path.write_bytes(content)
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
