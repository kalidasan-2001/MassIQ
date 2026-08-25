# R2 — Real Construction Plan Validation

This document is two things:

1. **Evidence** from the one real (non-synthetic, non-private) floor plan PDF already present in this dev environment (`backend/test_plan/floorplan.pdf`, untracked/gitignored per `*.pdf` in `.gitignore` — not committed here either).
2. **A manual validation procedure** for the private/customer construction PDFs this document deliberately does not commit, to be run before R2 is trusted against real-world plan variety beyond what one file can prove.

R2's automated test suite (`test_plan_service.py`, `test_plan_routes.py`, `test_pdf_inspection_service.py`) is *not* blocked on private PDFs — it runs entirely against the synthetic fixtures in `tests/pdf_fixtures.py`. This document exists to go one step further, not to gate the release.

## Evidence already gathered this session (real file, not synthetic)

`backend/test_plan/floorplan.pdf` — a real, single-page scanned/rastered floor plan sheet (841.92 × 595.32 pt, landscape) was run through the live API (`POST /api/projects`, then `POST /api/projects/{id}/plans`) with the actual dev Postgres + dev filesystem storage, not test doubles.

**First pass** (with the classifier's original `RASTER_IMAGE_COVERAGE_THRESHOLD = 0.8`): the page has one embedded raster image (bbox covering ~58% of the page area, i.e. ordinary print margins/title-block whitespace around the scan) and zero vector drawing commands. Result: `pdf_type: "unknown"` — the 0.8 threshold was calibrated only against synthetic full-bleed fixtures and didn't account for realistic scan margins.

**Fix applied**: `RASTER_IMAGE_COVERAGE_THRESHOLD` lowered to `0.5` (see `app/services/pdf_inspection_service.py`'s inline rationale). Re-running the identical file:

```json
{
  "processing_status": "ready",
  "pdf_type": "raster",
  "page_count": 1
}
```

Both the original file and its page-1 preview were confirmed resolvable on disk via `StorageService` afterward. This is the one piece of real-world calibration evidence R2 has; it is not a substitute for the broader validation below.

## Manual validation procedure (for private/customer PDFs)

Do not commit the PDFs used for this procedure to the repository. Run locally, record results in a local note (not checked in) or paste results into a PR description instead.

For each of the three categories below:

1. `docker compose up -d postgres` (repo root), backend running (`uvicorn app.main:app --reload --host 127.0.0.1 --port 8010`).
2. `POST /api/projects` with a throwaway project name.
3. `POST /api/projects/{project_id}/plans` with the real file (`multipart/form-data`, field name `file`).
4. Record: HTTP status, `processing_status`, `pdf_type`, `page_count`.
5. `GET /api/projects/{project_id}/plans/{plan_id}/pages` — record each page's `width`/`height`/`rotation`/`vector_content_available`, and cross-check `page_count` against what a PDF viewer reports.
6. Manually inspect the rendered preview PNG(s) under `backend/app/storage/plans/{plan_id}/pages/` — confirm they are legible and rotation-correct.
7. Delete the project afterward (or truncate the dev DB) so private data doesn't linger in the dev database indefinitely.

### Category 1 — real vector construction drawing (CAD-exported PDF)

Expect: `pdf_type: "vector"` (or `"mixed"` if the export embeds a raster title-block logo/stamp alongside real vector geometry — that is a correct, not a failing, result per the documented classification rules). Verify `vector_content_available: true` on pages with actual drawn geometry.

### Category 2 — real raster/scanned drawing

Expect: `pdf_type: "raster"`. If it instead comes back `"unknown"`, that is a signal `RASTER_IMAGE_COVERAGE_THRESHOLD` needs recalibrating again for that scan's margin proportions — treat as a finding to fix, not a silent pass.

### Category 3 — real multi-page drawing set

Expect: `page_count` equal to the actual page count, one `PlanPage` row per page in order, and page dimensions/rotation that match what a PDF viewer shows for each page (watch especially for a rotated page in the middle of a set, e.g. a landscape detail sheet inside an otherwise portrait set).

## Status

Not yet executed against real vector/raster/multi-page customer plans (no such files were available in this environment beyond the one raster scan documented above). This is a known gap, tracked as an open item for whoever has access to representative real plans — see the R2 checklist's Known Limitations.

---

## R2.5 calibration check (2026-08-25)

Per the R2.5 hardening scope: search this environment for any additional real (non-synthetic) PDFs before deciding whether to touch `RASTER_IMAGE_COVERAGE_THRESHOLD`, without redesigning the classifier or tuning it to force a pass.

**Search performed:** every `*.pdf` under `backend/app/storage/uploads/` (31 files, accumulated from prior manual dev/testing sessions) was opened and inspected (page count, `get_drawings()`, content-hash de-duplication) to find anything beyond the one already-documented raster scan.

**Result — no new usable evidence found:**

| Group (by content hash) | Count | What it actually is | Usable as real-plan calibration evidence? |
|---|---|---|---|
| Matches `test_plan/floorplan.pdf` exactly | 4 | The same real raster floor-plan scan, re-uploaded across sessions | Already counted — not new evidence |
| One 2-page PDF with vector drawings (`get_drawings() > 0` on both pages) | 1 | Opened and read: its extracted text is `"MassIQ Quantity Report ... E2E validation export test ..."` — this is a **PDF rendering of one of the app's own Excel/quantity-report exports** used as an end-to-end test artifact in a prior session, not a construction drawing. Its vector content is report table borders/lines, not floor-plan geometry. | **No** — real PDF, but not a real *construction plan*; would miscalibrate the classifier toward "report layouts count as VECTOR floor plans" |
| A trivial ~757-byte PDF, re-uploaded 23 times | 23 | Minimal/near-blank single-page PDF from routine manual endpoint testing (too small to contain meaningful geometry) | No |
| 3 more distinct small (~1KB) PDFs | 3 | Byte-for-byte the synthetic fixture `pdf_fixtures.py::build_vector_pdf_bytes()` output — created by this session's own new `test_legacy_upload_pdf.py` test run against the live filesystem, not a real plan | No (removed after inspection — this session's own test byproducts, never committed, not evidence) |

**Conclusion:** this environment still contains exactly **one** real, non-synthetic construction plan (`test_plan/floorplan.pdf`, RASTER, previously documented). No real vector construction drawing and no real multi-page construction drawing are available here.

**Per-category evidence status:**

| Category | Status | Evidence |
|---|---|---|
| Raster | **PASS (previously calibrated evidence, reconfirmed)** | Re-ran `open_and_validate` / `inspect_document` / `classify_document` against `test_plan/floorplan.pdf` this session: `image_coverage_ratio=0.5796`, `has_vector_drawings=False` → `PdfType.RASTER`. Identical result to the original R2 finding; `RASTER_IMAGE_COVERAGE_THRESHOLD=0.5` still correctly classifies this file. |
| Vector | **INSUFFICIENT CALIBRATION DATA** | No real vector construction drawing is available in this environment. Not tested; threshold left unchanged. |
| Multi-page | **INSUFFICIENT CALIBRATION DATA** | No real multi-page construction drawing is available in this environment (the one real multi-page file found is a 2-page app-generated report export, not a construction plan, and was excluded as unrepresentative). Threshold/behavior left unchanged. |

**Decision:** `RASTER_IMAGE_COVERAGE_THRESHOLD` and `MIXED_IMAGE_COVERAGE_THRESHOLD` in `pdf_inspection_service.py` are **unchanged** by R2.5. No tuning was performed to force any example to pass, and none was needed — the only real construction plan available still classifies correctly under the existing threshold.

**Consequence for R3:** per the R2.5 audit's explicit instruction, `pdf_type` must **not** become a hard business-rule branch (e.g. "block legend entry unless pdf_type == vector") until real vector and multi-page construction plans can be sourced and run through this same procedure. Until then, `pdf_type` should remain advisory/metadata in any UI that reads it.
