# R2 — Plan and PDF Ingestion: Acceptance Checklist

Date: 2026-08-14
Repository: `C:\Users\kalid\MassIQ`, branch `main` (verified via `git rev-parse --show-toplevel` and `git branch --show-current` before any change — see the final report's Repository verification section).
Scope: `Plan`/`PlanPage` models, `StorageService`, `PdfInspectionService`, multi-page rendering, `PlanService`, thin `/api/projects/{project_id}/plans*` routes, tests. No LegendEntry/HatchPattern/OCR/materials/analysis jobs/UI — none of that was touched, per R3+ exclusion.

Every item below was actually executed against the live PostgreSQL 16 instance (`massiq-postgres`, host port 5433) and a live FastAPI app. No item is marked PASS on code inspection or the previous review's report alone — the previous R2 attempt was found to not exist in this repository at all, so this checklist starts from the same forensic standard that review applied.

| # | Acceptance condition | Result | Evidence |
|---|---|---|---|
| 1 | Migration upgrade succeeds | **PASS** | `alembic upgrade head` → `Running upgrade 72c82e8ce581 -> 709345772063, create plans and plan_pages tables`. `\d plans` / `\d plan_pages` afterward show every column, FK (`plans.project_id -> projects.id ON DELETE CASCADE`, `plan_pages.plan_id -> plans.id ON DELETE CASCADE`), the `uq_plan_pages_plan_id_page_number` unique constraint, and both indexes (`ix_plans_project_id`, `ix_plan_pages_plan_id`) — matching the ORM models exactly. |
| 2 | Migration downgrade succeeds | **PASS** | `alembic downgrade -1` → `Running downgrade 709345772063 -> 72c82e8ce581`. Verified after: `\d plans` and `\d plan_pages` → "Did not find any relation"; `\dT+ plan_pdf_type` and `\dT+ plan_processing_status` → 0 rows (both enum types dropped — autogenerate's known gap, fixed manually in the migration file, same class of bug caught during R1). `projects` (the R1 table) confirmed still present and untouched throughout. |
| 3 | Migration re-upgrade succeeds | **PASS** | `alembic upgrade head` run again immediately after downgrade → succeeded cleanly. `\dt` afterward lists `alembic_version`, `plan_pages`, `plans`, `projects` — full schema restored. This full upgrade→downgrade→upgrade cycle was run against the real dev database, not simulated or assumed from a passing unit test. |
| 4 | Valid PDF upload | **PASS** | `test_plan_service.py::test_valid_vector_pdf_creates_ready_plan` + `test_plan_routes.py::test_upload_valid_vector_pdf_returns_201_ready` — green. Live smoke test: `POST /api/projects/{id}/plans` with a real PDF (`test_plan/floorplan.pdf`) → `201`, `processing_status: "ready"`. |
| 5 | PDF persistence | **PASS** | `test_plan_service.py::test_original_file_is_persisted_and_resolvable` (writes then resolves via a fresh `StorageService` call) + the cross-process proof below (a fully separate process resolved the original file after the writing process exited). |
| 6 | Multi-page support | **PASS** | `test_plan_service.py::test_multi_page_pdf_creates_matching_plan_page_rows` and `test_plan_routes.py::test_upload_multi_page_pdf`/`test_get_plan_detail_includes_pages_in_order`: a 3-page fixture produces exactly 1 `Plan` with `page_count == 3` and exactly 3 `PlanPage` rows, `page_number` sequential `[1, 2, 3]`, each with `width > 0`, `height > 0`, and a resolvable preview file. The 3rd page's forced 90° rotation is correctly recorded (`rotation == 90`) with swapped width/height (landscape), proving rotation is read from PyMuPDF's actual per-page state, not assumed constant across pages. |
| 7 | Vector classification | **PASS** | `test_pdf_inspection_service.py::test_vector_fixture_classified_vector` (`get_drawings() > 0`, `image_coverage_ratio == 0.0` → `VECTOR`) + `test_plan_routes.py` upload-level check. Rule is structural (drawing commands present, no significant raster coverage), not "text exists ⇒ vector" — verified explicitly by `test_text_alone_is_not_treated_as_vector_proof`. |
| 8 | Raster classification | **PASS** | `test_pdf_inspection_service.py::test_raster_fixture_classified_raster` (no drawings, `image_coverage_ratio ≈ 0.999` → `RASTER`) AND, more importantly, the real floor plan scan documented in `docs/testing/R2_REAL_PLAN_VALIDATION.md` — see Known Limitations for the calibration finding this surfaced and the fix applied. |
| 9 | Mixed classification | **PASS** | `test_pdf_inspection_service.py::test_mixed_fixture_classified_mixed` (drawings present AND `image_coverage_ratio ≈ 0.999` → `MIXED`) + `test_vector_and_raster_pages_together_force_mixed` (document-level aggregation: a VECTOR page and a RASTER page together force the document classification to MIXED, not an arbitrary pick of one). |
| 10 | Corrupt PDF rejection | **PASS** | `test_pdf_inspection_service.py::test_corrupt_pdf_rejected`, `test_plan_service.py::test_corrupt_pdf_rejected_and_nothing_persisted`, `test_plan_routes.py::test_upload_corrupt_file_returns_400` — a header-only/truncated-body PDF is rejected with `InvalidPdfError` → HTTP 400, zero DB rows, zero files written. |
| 11 | Fake PDF rejection | **PASS** | Plain text renamed `.pdf`: rejected at the `%PDF-` magic-byte check before `fitz.open` is even called. `test_upload_fake_text_file_returns_400` (400, no `Traceback` substring in the response body) + `test_fake_pdf_rejected_nothing_persisted_and_no_files_written` (zero DB rows, zero files on disk). Empty upload also covered (`EmptyFileError` from PyMuPDF, caught and converted to the same clean 400). |
| 12 | Preview persistence | **PASS** | `test_plan_service.py::test_multi_page_pdf_creates_matching_plan_page_rows` resolves every page's preview file via `StorageService.resolve_preview` and asserts it exists on disk. Cross-process proof (below) additionally resolved the preview from a second, independent process. |
| 13 | Old endpoint regression | **PASS** | Live smoke test against the running server (not just `app.openapi()` inspection): `POST /upload-pdf` → 200 with a real PDF, `GET /rendered-page/{id}` → 200, `POST /save-hatch-sample` → 200, `POST /detect-hatch` → 200 with real detections returned, `POST /export-excel` → 200. The full old chain was exercised end-to-end live, not assumed from route registration alone. |
| 14 | Old service regression | **PASS** | `hatch_detection.py`, `excel_service.py`, `vlm_service.py`, `measurement_service.py` were not modified (`git diff --stat HEAD` confirms). `pdf_service.py`'s existing `convert_pdf_first_page_to_png`/`suggest_plan_scale` functions are untouched byte-for-byte; only one new function (`render_page_to_png_bytes`) was added below them. |
| 15 | R1 regression | **PASS** | All 8 `test_project_service.py` + 12 `test_project_routes.py` + 10 `test_project_schemas.py` tests (30 total) still pass unmodified, including R1's own cross-engine persistence test. `backend/app/models/project.py`, `services/project_service.py`, `routes/projects.py`, `schemas/project.py` were not modified (only read). |
| 16 | Frontend build | **PASS** | `npm run build` → `✓ 85 modules transformed`, `✓ built in 1.76s`, no errors — identical module count to the R1 baseline build, confirming zero frontend changes. |

**R2 acceptance gate: 16/16 PASS.**

## Full regression totals

`python -m unittest discover -s tests -p "test_*.py"` → **114 tests, 0 failures** (57 pre-R2: 27 original MVP + 30 R1; 57 new R2: 16 `test_pdf_inspection_service.py` + 10 `test_storage_service.py` + 16 `test_plan_service.py` + 15 `test_plan_routes.py`).

## How to run this yourself

```bash
# 1. Start Postgres (repo root)
docker compose up -d postgres

# 2. Migrate (backend/)
cd backend
python -m alembic upgrade head

# 3. Run the full suite (spins up + migrates the separate massiq_test DB automatically)
python -m unittest discover -s tests -p "test_*.py"

# 4. Run the app
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

## Known limitations

- **Classification threshold calibration is based on one real PDF.** `RASTER_IMAGE_COVERAGE_THRESHOLD` was lowered from an initial 0.8 to 0.5 after testing against one real scanned floor plan (58% image coverage due to ordinary print margins) revealed the original value misclassified it as `UNKNOWN`. This is real evidence, not synthetic-only calibration — but it is still evidence from exactly one real file. `docs/testing/R2_REAL_PLAN_VALIDATION.md` documents the manual procedure for validating against real vector/raster/multi-page customer plans, which has not yet been executed for the vector or multi-page categories (no such real files were available in this environment). Flagged, not silently assumed to be fine.
- **No preview-serving HTTP endpoint.** `StorageService.resolve_preview`/`resolve_original_plan` work and are tested, but nothing in `routes/plans.py` streams the file bytes back over HTTP yet (deliberately out of the specified R2 route list — `POST`, `GET` list, `GET` detail, `GET` pages only). `PlanPageResponse` does not expose `preview_reference` to avoid leaking internal storage paths for a capability that doesn't exist yet.
- **Old `/upload-pdf` was deliberately left untouched, not adapted to `StorageService`.** This is intentional duplication per the instructions ("if adapting the old route increases risk, leave it untouched") — `main.py`'s `UPLOADS_DIR`/`RENDERED_DIR`/etc. constants and the new `StorageService`'s `plans/` root are two separate, non-overlapping storage layouts under `backend/app/storage/`.
- **No project-delete endpoint exists** (R1 scope decision, unchanged), so `Plan`'s `ON DELETE CASCADE` FK is currently unreachable via the API — it only protects against orphaned Plans if/when project deletion is added at the DB layer later.
- **`page.get_image_info()` bbox-sum coverage is an approximation**, not a true rendered-pixel coverage measurement — overlapping images on the same page would double-count area (not observed in any fixture or the one real PDF tested, but a real page with several overlapping raster layers could theoretically over-report coverage). Not fixed in R2; flagged as a refinement for Detection V2-era work if it ever proves material.

## Technical debt deliberately deferred

- `requirements-minimal.txt` still diverges from `requirements.txt` (unchanged from R1's decision) — no new R2 dependencies were needed (PyMuPDF/Pillow were already present), so this file was not touched at all in R2.
- No background job queue — `upload_plan` runs synchronously inside the HTTP request, consistent with "do NOT introduce complex distributed infrastructure prematurely" and matching R1's synchronous style.
- No structured/request-scoped logging around the new Plan routes (matches the existing app-wide absence of logging; not introduced here).
- `LegendEntry`, `HatchPattern`, `Analysis`, `Material`, `Measurement`, `Export` models: still do not exist, as instructed. R3+ scope.

## Deviations from the approved architecture

- **`RASTER_IMAGE_COVERAGE_THRESHOLD` was tuned mid-implementation** (0.8 → 0.5) based on real-PDF evidence gathered during this same implementation pass, documented above and in `docs/testing/R2_REAL_PLAN_VALIDATION.md` rather than left as a first-guess constant.
- **`PlanPage.width`/`height` are stored as `float` (PDF points), not the field's unspecified type** — chosen because PyMuPDF page geometry is not integral (e.g. A4 = 595.32×841.92pt) and because these represent the page's own logical dimensions, not a rendered preview's pixel size (documented in `PlanPage`'s docstring).
- **`PlanPageResponse` does not expose `preview_reference`** — an unrequested surface (a preview-serving endpoint) was not built, so internal storage paths are not exposed either; see Known Limitations.
- No other deviations. `Plan`/`PlanPage` field lists, enum value sets, route paths, and the `PlanService.upload_plan` orchestration order all match the R2 instructions as given.
