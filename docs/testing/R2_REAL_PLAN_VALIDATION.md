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
