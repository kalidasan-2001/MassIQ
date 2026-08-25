# MassIQ — Current State Audit

Date: 2026-08-13
Scope: forensic, read-only audit of the git-tracked repository (`git ls-files`, 44 files). No production behavior was modified to produce this document.

This audit deliberately ignores four large untracked directories sitting in the working tree (`_backup_before_flatten/`, `_recovery_candidates/`, `_live_before_validated_restore_*/`, `massiq-mvp/`) — they are gitignored recovery snapshots from a prior "flatten" migration, not part of the shipping app. They are noted under Technical Debt because their continued presence on disk is confusing, but no file inside them was treated as current source.

---

## Confirmed existing behavior

Verified by reading the actual route/service/component code (not by trusting `docs/*.md`, which are stale — see Technical Debt).

**Backend** — FastAPI app (`backend/app/main.py`), single process, no DB, filesystem-only storage under `backend/app/storage/` (gitignored, created on startup).

| Route | Method | File | Behavior |
|---|---|---|---|
| `/` , `/health` | GET | `main.py` | liveness |
| `/upload-pdf` | POST | `main.py` | validates `.pdf` extension only, saves raw bytes to `storage/uploads/{uuid}.pdf`, renders page 0 to PNG via PyMuPDF |
| `/rendered-page/{file_id}` | GET | `main.py` | streams the rendered PNG |
| `/suggest-plan-scale/{file_id}` | POST | `main.py` → `pdf_service.suggest_plan_scale` | regex on the **filename stem** for a `1:NNN` pattern; not real OCR |
| `/analyze-section/{section_file_id}` | POST | `main.py` → `measurement_service` | regex on filename stem; placeholder |
| `/save-hatch-sample` | POST | `routes/detection.py` | crops the rendered PNG to a user bbox, stores `storage/hatch_samples/{uuid}.png` |
| `/detect-hatch` | POST | `routes/detection.py` → `hatch_detection.detect_hatch_regions` | grayscale OpenCV `matchTemplate`, multi-scale (8 fixed scale steps + native), confidence-weighted size filter, center-proximity merge, hard cap 200 detections |
| `/export-excel` | POST | `routes/export.py` → `excel_service.build_excel_report` | single-sheet openpyxl workbook from a fully frontend-computed payload; streamed as a download, nothing persisted server-side |
| `/vlm/analyze-floor-plan`, `/vlm/analyze-section-view`, `/vlm/suggest-legend-hatch` | POST | `routes/vlm.py` → `vlm_service.py` | optional OpenAI Responses API calls (`gpt-4.1-mini`, `temperature=0`); every function degrades to a valid empty/fallback shape if `OPENAI_API_KEY` is unset or any step fails — never raises to the caller |

**Frontend** — single-page React 18 + Vite app, no router, no global state library. `PlanViewer.jsx` (641 lines) owns essentially all workflow state as local `useState`. Component tree matches `CLAUDE.md`'s description exactly (verified against source, not assumed). A 4-step wizard (`stepDefs` in `PlanViewer.jsx`) gates progression: Upload & Scale → Select Component → Review Quantity → Export.

The quantity formula lives in exactly one place, `frontend/src/utils/quantityEngine.js`, a pure function with no backend counterpart:
```
final_area_m2 = accepted_detection_area_m2 + added_correction_area_m2 - subtracted_correction_area_m2
volume_m3     = final_area_m2 × confirmed_height_m
```
`/export-excel`'s Pydantic model (`ExportPayload`) accepts `area_m2`/`volume_m3` as plain floats and writes them verbatim — the backend does not and cannot recompute them. This matches CLAUDE.md's "never sent to or computed by the backend" claim and satisfies PRIMARY Rule 2 (deterministic quantity, AI never decides it) already, today.

Human-in-the-loop (Rule 3) is also already implemented: `DetectionReviewPanel.jsx` gives per-detection accept/reject/delete; `RegionEditor.jsx` gives manual add/subtract correction boxes with optional window/door deduction tagging; nothing reaches `quantityEngine` except what the user explicitly accepted or drew.

**Coordinate handling**: display-space ↔ natural-image-space conversion is centralized in two functions in `PlanViewer.jsx` (`toRectFromDraft`, `toDisplayRect`), not scattered — this is the one piece of "coordinate utility" the target architecture asks for, already done, just not extracted into a shared module (frontend-only; there's no PDF-point ↔ image-pixel layer yet since nothing currently reads vector PDF coordinates).

## Existing reusable modules

These are real assets to build on top of, not replace:

- `services/pdf_service.py::convert_pdf_first_page_to_png` — deterministic PyMuPDF render at fixed 2× zoom matrix, capped at 1800px wide. Correct place to extend for multi-page and rotation, per Phase 7.
- `services/hatch_detection.py` — self-contained, already unit-tested (`tests/test_hatch_detection.py`, 2 test classes covering the size-quality filter and multi-scale matching), already has a documented "one signal, not the only signal" shape (scale sweep, confidence-weighted filtering, capped candidates) that maps cleanly onto the future Detection V2 "template matching as fallback/baseline" role.
- `services/excel_service.py::build_excel_report` — pure function, payload-in/bytes-out, already tested (`tests/test_excel_service.py`). Safe to keep calling from a thin route indefinitely.
- `frontend/src/utils/quantityEngine.js` — the one deterministic-math module; must not be duplicated anywhere else (Rule/code-quality item already satisfied — verified no other file computes `final_area_m2` or `volume_m3`).
- `vlm_service.py`'s fallback pattern (never raise; always return a valid empty shape keyed by the same schema as success) is a good template to reuse for any new AI-assisted suggestion endpoint (e.g. future OCR-based legend description reading).
- `HatchDetectionPanel.jsx`'s `normalizeDetections` — the one place that converts backend detection px → `area_m2` using `scale.pixelsPerMeter`; reuse this shape rather than inventing a second one when detections start coming from a job/async source.

## Technical debt

- **Root working tree pollution**: `_backup_before_flatten/` (92MB, includes a checked-out `venv/` with compiled `cv2` binaries), `_recovery_candidates/`, `_live_before_validated_restore_20260513_080814/`, and `massiq-mvp/` all sit at the repo root, gitignored but present on disk. `README.md` still narrates this recovery story as the primary repo description instead of describing the actual app. None of this blocks R1/R2 work but it should eventually be deleted from disk (never was in git history per `git log --all -- _backup_before_flatten` returning nothing) and `README.md` rewritten.
- **Dead/empty files tracked in git**: `backend/app/main_simple.py`, `backend/app/services/vlm_usage_tracker.py`, `backend/README.md`, `backend/app/routes/detection_patch.txt` are all 0 bytes but committed. `main_simple.py`'s name suggests an abandoned alternate entrypoint; nothing imports it. Safe-to-delete candidates once confirmed unused (see "Safe to refactor").
- **Two divergent requirements files**: `requirements.txt` (13 pkgs incl. `pandas`, `reportlab`, `rapidocr-onnxruntime`, `opencv-python`) vs `requirements-minimal.txt` (12 pkgs, `opencv-python-headless` instead, no `pandas`/`rapidocr`). Nothing in the codebase imports `pandas`, `reportlab`, or `rapidocr_onnxruntime` (grep-verified) — both files carry unused/aspirational dependencies. `main.py` only needs what `requirements-minimal.txt` has, minus even `reportlab`/`rapidocr`. No documented rule for which file `pip install` is supposed to target — `CLAUDE.md`'s own setup instructions say `pip install -r requirements.txt`, the heavier file.
- **Stale, self-contradicting docs under `docs/`**: `SYSTEM_STATUS.txt` and `TESTING_STATUS.txt` are dated 2025-05-08, reference `massiq-mvp/backend` and `massiq-mvp/frontend` paths (pre-flatten layout) and port 8000 (current backend runs on 8010 per `CLAUDE.md` and `main.py`'s own docstring intent). `OPTIMIZATION_REPORT.md`, `PHASE_14_SUMMARY.md`, `README_TESTING.md`, `TESTING_CHECKLIST.md` total >1300 lines of historical narrative that may or may not still be accurate — none were used as a source of truth for this audit; all facts above were re-derived from source. These should be archived (not deleted — they may have investigative value) rather than left presented as current status.
- **No CI, no Docker**: confirmed via filesystem search — no `.github/workflows/`, no `Dockerfile`, no `docker-compose.yml` anywhere in the tracked tree. `docs/architecture/TARGET_ARCHITECTURE.md`'s "Object/file storage" layer and Phase 2's Postgres introduction will need a local dev story (docker-compose for Postgres at minimum) that doesn't exist today.
- **No persistence beyond the filesystem**: every "record" (uploaded PDF, rendered page, hatch sample) is a bare file keyed by a UUID with zero metadata — no project, no plan row, no relationship between a `file_id` and any user-facing concept. `PlanViewer.jsx`'s `projectName` field is pure local UI state, submitted only inside the Excel export payload; it is never persisted or connected to `file_id`. This is exactly the gap R1/R2 exist to close.
- **`/upload-pdf` only ever processes page 0.** `pdf_service.convert_pdf_first_page_to_png` hardcodes `doc.load_page(0)`; `doc.page_count` is returned but nothing downstream uses page 2+. Multi-page support (Phase 6/Test C) does not exist yet at all, not even partially.
- **No file-type/corruption validation on upload.** `/upload-pdf` checks only that the filename ends in `.pdf` (client-controlled string, not content sniffing) before handing the bytes to `fitz.open`. A non-PDF renamed `.pdf` or a corrupted file will raise inside `convert_pdf_first_page_to_png` with whatever exception PyMuPDF throws, which FastAPI will turn into an unhandled 500 — Test F (invalid PDF) would fail today. There is no try/except around the PyMuPDF call in `main.py`.
- **`suggest_plan_scale` and `analyze_section_dimensions` are filename-regex heuristics, not real inspection**, despite living in `pdf_service.py`/`measurement_service.py` — the docstring-level intent ("placeholder for real OCR") is honest but this means Phase 6 (vector/raster inspection) has zero existing implementation to build on; it starts from scratch.
- **CORS is wide open** (`allow_origins=["*"]`, `allow_credentials=True`) — fine for local MVP dev, flagged so it isn't carried forward unexamined into a persistence-backed release with real project data.
- **`frontend/tsconfig.json` exists but the codebase is 100% `.jsx`**, not `.ts`/`.tsx` — the "typed frontend API contracts" code-quality rule in the instructions has no current type layer to extend; this is a gap to flag for Phase 4+ (project/plan API client), not something R1/R2 needs to fix, but worth deciding on (JSDoc types vs migrating to TS) before building new typed API surfaces.
- **`_normalize_scale_steps` in `hatch_detection.py`** silently `set()`-dedupes and always re-adds `1.0` — reasonable, but the 8 magic scale constants (`DEFAULT_SCALE_STEPS`) and the two hard caps (`MAX_RAW_CANDIDATES_PER_SCALE=200`, `MAX_TOTAL_DETECTIONS=200`) are module-level constants, not environment/config-driven — matches the "no arbitrary magic thresholds without named configuration" rule only partially (they're named, not configurable). Not blocking for R1/R2; relevant when Detection V2 work starts.

## Missing infrastructure

- No database of any kind (no SQLAlchemy/Alembic/psycopg2 in either requirements file).
- No storage abstraction — `UPLOADS_DIR` / `RENDERED_DIR` / `HATCH_SAMPLES_DIR` / `EXPORTS_DIR` are module-level `Path` constants computed independently in `main.py` and `routes/detection.py` (duplicated `BASE_DIR = Path(__file__).resolve().parent[s]` logic, slightly different in each file), and used directly as filesystem paths inside route handlers.
- No project/plan/page domain model — no ORM models, no Pydantic domain schemas beyond the per-route request/response bodies.
- No background job system — detection and export both run synchronously inside the HTTP request.
- No structured logging — no `logging` calls found anywhere in `backend/app` (grep-verified); errors surface only as FastAPI's default exception responses.
- No environment-driven configuration object — `os.getenv("OPENAI_API_KEY")` / `os.getenv("OPENAI_VLM_MODEL", "gpt-4.1-mini")` are called ad hoc inside `vlm_service.py`; no central `Settings`/`config.py`.
- No test runner config beyond raw `unittest` files (no `pytest.ini`/`pyproject.toml` `[tool.pytest]`, no `package.json` test script beyond the Playwright smoke script, which depends on a hardcoded absolute path to a PDF inside the gitignored `_backup_before_flatten/` folder — `frontend/playwright.smoke.run.js:3` — meaning `npm run smoke:all` is not currently runnable from a clean checkout).

## Must preserve

- The deterministic quantity formula and its single-source-of-truth location (`quantityEngine.js`), and the fact that `/export-excel` never recomputes it.
- The human-in-the-loop review/correct/tag flow (`DetectionReviewPanel`, `RegionEditor`) and its output shape (`acceptedDetections`, `corrections[]` with `kind: 'add'|'subtract'`).
- `hatch_detection.py`'s public function signature and behavior (`detect_hatch_regions(...)` → list of `{id,x,y,w,h,confidence,selected,status}`), and its existing test suite.
- `excel_service.build_excel_report`'s payload contract and existing test suite (row positions are asserted exactly by `test_excel_service.py`).
- The `/upload-pdf` → `/rendered-page/{file_id}` → `/save-hatch-sample` → `/detect-hatch` → `/export-excel` endpoint names and shapes as *externally observable* contracts, per the Migration Rule ("do not rename existing public API routes without a migration reason") — R1/R2 should wrap/extend, not rename, until a documented reason exists.
- The graceful-fallback contract of every `vlm_service.py` function (never raises to caller on missing key/network/parsing failure).

## Safe to refactor

- `main.py`'s inline `STORAGE_DIR`/`UPLOADS_DIR`/etc. constants and directory creation — natural first extraction into a `StorageService` (Phase 3) since nothing else depends on the exact module-level variable names, only on the resulting file paths being stable.
- `routes/detection.py`'s independently-computed `BASE_DIR`/`STORAGE_DIR` (duplicated from `main.py`) — should collapse onto one shared config/storage module.
- The 0-byte tracked files (`main_simple.py`, `vlm_usage_tracker.py`, `backend/README.md`, `detection_patch.txt`) — pending a quick confirmation grep (done: nothing imports `main_simple` or `vlm_usage_tracker`; `main.py` only imports from `app.routes` and `app.services.{measurement_service,pdf_service}` plus what those import), these can be deleted rather than refactored.
- `docs/SYSTEM_STATUS.txt`, `docs/TESTING_STATUS.txt`, `docs/OPTIMIZATION_REPORT.md`, `docs/PHASE_14_SUMMARY.md`, `docs/README_TESTING.md`, `docs/TESTING_CHECKLIST.md` — candidates to move under something like `docs/history/` so `docs/` stops mixing stale historical status reports with the new `docs/architecture/` and `docs/releases/` material this task is introducing.

## Unknown / requires verification

- Whether any real (non-synthetic) construction PDFs exist anywhere accessible for R1/R2's required acceptance tests (multi-page, vector, raster, invalid). The Playwright smoke test references `_backup_before_flatten/massiq-mvp-backup/massiq_e2e.pdf`, which is present on disk but untracked and not guaranteed to represent the variety Test C–F require. **Needs a test-fixture PDF set before R1/R2 acceptance testing can run** (flagging for the test plan below rather than assuming).
- Whether `OPENAI_API_KEY` is available in the current dev environment (`backend/.env`, gitignored) — not required for R1/R2 since VLM is optional/fallback-safe, but relevant to know for Test G regression coverage of the VLM routes.
- The actual page count / structure of whatever "6 test PDFs" `docs/TESTING_STATUS.txt` refers to — that file is stale and the PDFs it names are not confirmed to still exist at the paths it lists (`massiq-mvp/backend/app/storage/uploads/`, pre-flatten).
- Deployment target/environment for a future Postgres instance (local Docker vs. managed) — not specified anywhere in the repo; will need a decision before Phase 2 implementation, not before this assessment.

---
*This document describes state only. See the accompanying assessment message for the proposed R1/R2 migration plan, file-by-file changes, and Definition of Done.*
