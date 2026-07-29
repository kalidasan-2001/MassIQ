# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MassIQ is a construction quantity takeoff MVP. Users upload a PDF floor plan, confirm a scale, pick a hatch pattern sample from the legend, run automatic detection across the plan, review and correct detections, confirm element height, then export a quantity (area + volume) report to Excel.

The only supported component out of the box is "Stahlbeton C25/30" (reinforced concrete), but the component name field is free text.

## Commands

### Backend

```bash
# Install dependencies (Python 3.10+, create venv first)
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Run dev server (port 8010)
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Health check: `curl http://127.0.0.1:8010/health`

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173
npm run build      # production build to frontend/dist/
npm run preview    # serve the dist/ build locally
```

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | *(none)* | Enables VLM analysis; backend gracefully falls back if absent |
| `OPENAI_VLM_MODEL` | `gpt-4.1-mini` | OpenAI model used for floor-plan and section analysis |
| `VITE_API_BASE_URL` or `VITE_BACKEND_URL` | `http://127.0.0.1:8010` | Frontend API base URL |

## Architecture

### Backend (`backend/app/`)

FastAPI application split across three routers, all registered in `main.py`:

| Module | Prefix | Responsibility |
|---|---|---|
| `main.py` | `/` | PDF upload → PNG render, `/rendered-page/{id}`, scale suggestion |
| `routes/detection.py` | `/` | Save hatch sample crop (`/save-hatch-sample`), run detection (`/detect-hatch`) |
| `routes/vlm.py` | `/vlm` | Optional AI analysis of floor plans and section drawings |
| `routes/export.py` | `/` | `/export-excel` — streams an .xlsx file |

**Services:**

- `services/pdf_service.py` — converts PDF page 0 to PNG at 2× zoom, capped at 1800 px wide (PyMuPDF / `fitz`)
- `services/hatch_detection.py` — OpenCV `matchTemplate` (grayscale, `TM_CCOEFF_NORMED`); merges nearby matches; hard cap of 200 detections
- `services/vlm_service.py` — encodes image as base64 data URL, calls OpenAI Responses API; returns graceful fallback dict if `OPENAI_API_KEY` is unset
- `services/measurement_service.py` — heuristic regex-based height suggestion from filename stem; placeholder for real OCR
- `services/excel_service.py` — builds a single-sheet openpyxl workbook and returns raw bytes

**File storage** — all runtime files are under `backend/app/storage/` (gitignored):
- `uploads/` — original PDFs
- `rendered_pages/` — PNG renders (and `section_<id>.png` for sections)
- `hatch_samples/` — cropped hatch pattern PNGs
- `exports/` — reserved for future use

Files are keyed by UUID hex `file_id`. All directories are auto-created on startup.

### Frontend (`frontend/src/`)

Single-page React app (Vite, no router). All workflow state lives in `PlanViewer.jsx`.

**Component tree and responsibilities:**

```
App.jsx
└── UploadPanel.jsx        — PDF upload form; persists last file_id to localStorage
    └── PlanViewer.jsx     — main workspace; owns ALL workflow state
        ├── LegendAssistantPanel.jsx  — draws legend area + hatch sample bbox on the plan image
        ├── HatchDetectionPanel.jsx   — calls /detect-hatch, normalises results to {x,y,w,h,area_m2}
        ├── DetectionReviewPanel.jsx  — accept / reject individual detection bboxes
        ├── RegionEditor.jsx          — draw add / subtract correction regions on top of accepted detections
        ├── SectionHeightPanel.jsx    — height / thickness confirmation (feeds quantityEngine)
        └── ExportButton.jsx          — calls /export-excel, triggers browser download of .xlsx
```

**Key state in `PlanViewer.jsx`:**

| State | Purpose |
|---|---|
| `scale` | `{ pixelsPerMeter }` — set by the user from pixel/real-distance inputs |
| `hatchSample` | `{ hatch_sample_id }` — returned by `/save-hatch-sample` |
| `rawDetections` / `acceptedDetections` | full list vs. after review |
| `corrections` | array of `{ kind: 'add'|'subtract', x, y, w, h, area_m2 }` |
| `heightMeters` / `heightConfirmed` | user-typed height; quantity is blocked until confirmed |

**Coordinate system** — the plan image is displayed at whatever size the browser renders it. All user interactions (mouse events, bounding box overlays) are converted between display-space and natural-image-space using `toRectFromDraft` / `toDisplayRect` in `PlanViewer.jsx`.

**Quantity formula** (computed in `utils/quantityEngine.js`, pure function):
```
final_area_m2 = accepted_detection_area_m2 + added_correction_area_m2 - subtracted_correction_area_m2
volume_m3     = final_area_m2 × confirmed_height_m
```
The final volume is **never sent to or computed by the backend** — it is deterministic frontend-only math.

**API client** (`src/api/api.js`) — a single axios instance; timeout 120 s (long PDF renders).

### Workflow sequence

1. `POST /upload-pdf` → backend saves PDF, renders page 0 to PNG, returns `file_id` + image dimensions
2. User sets scale (pixels per meter) in the frontend — no backend call
3. `POST /save-hatch-sample` → backend crops the PNG to the user's bbox, returns `hatch_sample_id`
4. `POST /detect-hatch` → backend runs template matching, returns list of detection bboxes
5. User reviews detections, adds correction regions — all frontend state
6. User confirms height — frontend computes `quantityEngine.buildQuantityResult()`
7. `POST /export-excel` → backend builds openpyxl workbook, streams it as blob download
