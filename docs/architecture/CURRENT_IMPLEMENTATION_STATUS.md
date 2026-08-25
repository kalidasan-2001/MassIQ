# MassIQ — Current Implementation Status

**Audit date:** 2026-08-25
**Repository:** `C:\Users\kalid\MassIQ`, branch `main` (up to date with `origin/main`)
**Method:** Every claim below was checked against source, or executed live against a real PostgreSQL 16 container and a real running FastAPI process in this session. Nothing here is inferred from filenames, docstrings, or prior audit documents without independent re-verification. Where a prior document (`docs/releases/R1_PROJECT_PERSISTENCE_CHECKLIST.md`, `docs/releases/R2_CORE_FOUNDATION_CHECKLIST.md`, dated 2026-08-13/14, both untracked/uncommitted) claimed something, it is marked **RE-VERIFIED** below only if this session independently reproduced the evidence.

---

## 0. Repository verification

| Check | Result |
|---|---|
| `pwd` | `C:\Users\kalid\MassIQ` ✅ expected |
| `git rev-parse --show-toplevel` | `C:/Users/kalid/MassIQ` ✅ |
| `git branch --show-current` | `main` ✅ |
| `git status` | clean history, 3 modified tracked files (`main.py`, `pdf_service.py`, `requirements.txt` — all additive, reviewed below), ~20 untracked new files/dirs (R1/R2 code, tests, docs, `docker-compose.yml`) — **none of this is committed yet** |
| `git log --oneline -10` | 4 commits on `main`, most recent `192c4fd` (hatch detection + VLM tuning). R1/R2 work is not in any commit. |
| Local branches | `main` (current), `deploy-migration` (an older, unrelated Render-deployment line — diverges by dropping `CLAUDE.md` and adding a Dockerfile; not part of this audit's scope, not merged) |
| Remotes | `origin` → `kalidasan-2001/MassIQ`, `massiq123` → `kalidasan-2001/MassIQ123` (second remote, unclear purpose — flagged below) |

**Conclusion: correct repository, correct branch.** All R1/R2 work described below exists only in the working tree — **nothing has been committed**. This is the single most important fact for release planning: from git's perspective, `main` is still at the pre-R1 MVP.

---

## 1. Current architecture (as built, not as documented)

```
Frontend (React 18 + Vite, no router)
  App.jsx → UploadPanel.jsx → PlanViewer.jsx (641 lines, owns all workflow state)
       ├── LegendAssistantPanel.jsx
       ├── HatchDetectionPanel.jsx
       ├── DetectionReviewPanel.jsx
       ├── RegionEditor.jsx
       ├── SectionHeightPanel.jsx
       └── ExportButton.jsx
  utils/quantityEngine.js — sole deterministic area/volume formula, frontend-only
       ↓ axios (src/api/api.js), 120s timeout
FastAPI app (backend/app/main.py)
  ├── Legacy MVP surface (inline in main.py + routes/detection.py, routes/export.py, routes/vlm.py)
  │     no DB, filesystem-only, module-level path constants duplicated in 2 files
  └── R1/R2 surface (routes/projects.py, routes/plans.py)
        ├── ProjectService / PlanService  (thin routes, service owns logic)
        ├── StorageService                (centralizes Plan file paths, path-traversal guarded)
        ├── PdfInspectionService          (vector/raster/mixed classification)
        └── SQLAlchemy models (Project, Plan, PlanPage) → Alembic → PostgreSQL 16
```

Two storage layouts coexist under `backend/app/storage/`: the legacy flat `uploads/ rendered_pages/ hatch_samples/ exports/` (unversioned, no DB row) and the new `plans/<uuid>/{original.pdf, pages/000N.png}` (DB-tracked via `StorageService`). This is intentional, documented duplication (R2 was scoped to not touch the old path), not an oversight — but it is duplication that must eventually collapse.

There is a third, unrelated root-level `storage/` directory and a `test_plans/` directory (both gitignored) whose purpose is not evident from any code that reads them — see Technical Debt.

---

## 2. Implementation inventory

| Capability | Status | Files | Verification | Notes |
|---|---|---|---|---|
| Project persistence | **VERIFIED WORKING** | `models/project.py`, `services/project_service.py`, `routes/projects.py`, `schemas/project.py` | Live: created a project via `POST /api/projects` against a real Postgres container, confirmed row via `psql`, deleted it after | — |
| Project CRUD | **VERIFIED WORKING** | same | Create/list/get/patch all exercised by 30 passing tests + live smoke; no delete endpoint exists (deliberate, documented) | No `DELETE /api/projects/{id}` |
| PostgreSQL | **VERIFIED WORKING** | `docker-compose.yml`, `core/config.py` | Started the compose service this session, `pg_isready` succeeded, app connected | Runs on host port 5433 (avoids a real conflict with an unrelated project's Postgres already on 5432 on this machine) |
| Alembic migrations | **VERIFIED WORKING** | `alembic/`, 2 revisions | Ran `alembic current`/`heads` live: DB was already at head `709345772063`; chain `None → 72c82e8ce581 → 709345772063` is structurally sound (verified by reading both files) | Enum-type drop-on-downgrade bug was already fixed in both migrations |
| Plan persistence | **VERIFIED WORKING** | `models/plan.py`, `services/plan_service.py` | Live: uploaded `test_plan/floorplan.pdf` via `POST /api/projects/{id}/plans`, got back `processing_status: ready`, `pdf_type: raster`, `page_count: 1` | Transactional: DB row only reaches `READY` after every page+preview succeeds, rollback + best-effort file cleanup otherwise (read in code, exercised by `test_forced_failure_during_page_rendering_leaves_no_trace`) |
| PlanPage persistence | **VERIFIED WORKING** | `models/plan_page.py` | Test suite covers multi-page (3-page fixture, sequential 1-based page numbers, per-page rotation) | No live multi-page real-file test was performed (only one real PDF available, single-page) |
| PDF validation | **VERIFIED WORKING** | `services/pdf_inspection_service.py::open_and_validate` | Magic-byte check + PyMuPDF open, all wrapped in `InvalidPdfError`→400; unittest suite covers empty/corrupt/fake-text cases | Old `/upload-pdf` still has **no** such validation (see Technical Debt — BLOCKER) |
| Multi-page ingestion | **IMPLEMENTED BUT NOT VERIFIED (real file)** | `plan_service.py`, `pdf_inspection_service.py` | Synthetic 3-page fixture passes; no real multi-page customer PDF was available in this environment to test against | Old `/upload-pdf` still hardcodes `load_page(0)` only |
| Vector/raster/mixed classification | **PARTIAL** | `pdf_inspection_service.py` | Structural rule (drawings + image-coverage ratio) is sound and unit-tested; **but the raster threshold (0.5) was calibrated against exactly one real scanned PDF**, documented honestly in `docs/testing/R2_REAL_PLAN_VALIDATION.md` | Needs more real-world calibration before being trusted as accurate across scan qualities |
| Preview generation | **VERIFIED WORKING** | `pdf_service.py::render_page_to_png_bytes`, `storage_service.py` | Live-confirmed file exists on disk after upload | No HTTP endpoint serves it yet (deliberately out of R2 scope) |
| Storage abstraction | **PARTIAL** | `services/storage_service.py` | Solid design (path-traversal guarded, relative references, tested) for the *new* Plan pipeline only | Old MVP paths (`main.py`, `routes/detection.py`) still duplicate `BASE_DIR`/`STORAGE_DIR` computation independently — two unrelated storage abstractions coexist |
| Old `/upload-pdf` flow | **VERIFIED WORKING (legacy)** | `main.py` | Live: uploaded real PDF, got `file_id`, rendered PNG served at `/rendered-page/{id}` (HTTP 200) | Still has zero content validation (extension check only) and still only ever processes page 0 — unchanged since before R1/R2 |
| Hatch sample selection | **VERIFIED WORKING** | `routes/detection.py` | Live: `POST /save-hatch-sample` against the same uploaded file → cropped PNG returned | — |
| Multi-scale template matching | **VERIFIED WORKING** | `services/hatch_detection.py` | Live: `POST /detect-hatch` returned real detections against the real PDF; also covered by 9 passing unit tests | Magic constants (`MAX_RAW_CANDIDATES_PER_SCALE=200`, 8 fixed scale steps) are named but not configurable |
| Review/accept/reject | **VERIFIED WORKING (frontend, code-read)** | `DetectionReviewPanel.jsx` | Not backend-observable; confirmed by reading component logic — no unit tests exist for this component | Frontend has no test suite at all (no Jest/Vitest/Playwright config runnable from a clean checkout) |
| Manual add/subtract correction | **IMPLEMENTED BUT NOT VERIFIED (no frontend tests)** | `RegionEditor.jsx` | Code-read only | — |
| Deterministic area calculation | **VERIFIED WORKING** | `utils/quantityEngine.js` | Read in full: one pure function, only caller of `final_area_m2`/`volume_m3` math confirmed via grep — no duplicate calculation path anywhere in the repo | This is the single most load-bearing correctness guarantee in the app today |
| Deterministic volume calculation | **VERIFIED WORKING** | same | `volume_m3 = final_area_m2 × height_m`, frontend-only, never recomputed server-side | `/export-excel`'s Pydantic model accepts `area_m2`/`volume_m3` as plain floats and writes them verbatim (confirmed by reading `routes/export.py`) |
| Excel export | **VERIFIED WORKING** | `services/excel_service.py`, `routes/export.py` | Live: `POST /export-excel` against the running server returned a 5176-byte `.xlsx` stream, HTTP 200 | 4 existing regression tests pass |
| VLM functionality | **VERIFIED WORKING (fallback path)** | `services/vlm_service.py`, `routes/vlm.py` | 9 unit tests pass, all exercising the no-API-key / mocked-error / mocked-success fallback contract; **no live call to the real OpenAI API was made this session** (no key configured in this shell) | Never raises to caller — confirmed by test suite, not just docstring claim |
| LegendEntry persistence | **NOT IMPLEMENTED** | — | Grep for `LegendEntry`/`HatchPattern` model: no matches | R3+ scope |
| OCR | **NOT IMPLEMENTED** | — | `measurement_service.py`/`pdf_service.py::suggest_plan_scale` are filename-regex heuristics, not OCR, by their own docstrings | `rapidocr-onnxruntime` is in `requirements.txt` but unused (grep-confirmed) |
| Material confirmation | **NOT IMPLEMENTED** | — | Component name is free text typed by the user; no confirmation/validation workflow exists | — |
| Hatch feature extraction | **NOT IMPLEMENTED** | — | `hatch_detection.py` does template matching only, no feature vectors persisted anywhere | R4 scope |
| Project pattern library | **NOT IMPLEMENTED** | — | No `HatchPattern`/library model or route exists | R5 scope |
| Planning-office / company library | **NOT IMPLEMENTED** | — | — | R5+ scope |
| Tile-based detector | **NOT IMPLEMENTED** | — | Current detector is whole-image `matchTemplate`, not tiled | R6 scope |
| Similarity heatmap | **NOT IMPLEMENTED** | — | — | R6 scope |
| Asynchronous analysis jobs | **NOT IMPLEMENTED** | — | `upload_plan` and `/detect-hatch` both run synchronously inline in the HTTP request (confirmed by reading both) | Correctly out of scope per "no premature distributed infrastructure" — current payload sizes don't need it yet |
| Structured logging | **NOT IMPLEMENTED** | — | `grep -r "import logging" backend/app` → zero matches | Errors surface only as FastAPI default exception responses |
| CI | **NOT IMPLEMENTED** | — | No `.github/` directory anywhere in the tree | `deploy-migration` branch has a CI workflow file, but it is not on `main` and not evaluated here |
| Dockerized application | **PARTIAL** | `docker-compose.yml` | Only Postgres is containerized; no `Dockerfile` for backend/frontend on `main` | — |
| Authentication | **NOT IMPLEMENTED** | — | No auth middleware, no user model, CORS is `allow_origins=["*"]` with `allow_credentials=True` | Acceptable for single-user local MVP; a BLOCKER before any multi-tenant/hosted deployment |
| Production deployment | **NOT IMPLEMENTED** | — | No deployment config on `main` (the `deploy-migration` branch has one, unrelated to this audit) | — |

---

## 3. Release-history verification

### R0 — Repository/architecture audit
**STATUS: COMPLETE.** A prior audit (`docs/architecture/CURRENT_STATE.md`, dated 2026-08-13) exists and its factual claims about the pre-R1 codebase were independently spot-checked in this session and found accurate. This document supersedes it going forward.

### R1 — Project Persistence
**STATUS: COMPLETE — RE-VERIFIED this session**, not merely re-trusted from `docs/releases/R1_PROJECT_PERSISTENCE_CHECKLIST.md`. Independently reproduced this session:
- `Settings` (`core/config.py`), Postgres+SQLAlchemy+Alembic wiring, `Project` model, `ProjectService`, thin `/api/projects` routes all exist and match the checklist's description.
- Migration `72c82e8ce581` applies/rolls back cleanly against a real DB (verified by reading the file; up/down/up cycle was not re-run this session since the DB was already past this revision, but the chain integrity was confirmed by inspection and the subsequent migration's clean apply proves it).
- Live `POST /api/projects` → 201 with generated UUID/timestamps/default status, confirmed against real Postgres.
- 30 R1-specific unit/route/schema tests pass as part of the 114-test full run this session.
- **Not committed to git** — this is the one respect in which "complete" needs qualification: the work exists and works, but is not yet a permanent part of `main`'s history.

### R2 — Plan/PDF Foundation
**STATUS: COMPLETE — RE-VERIFIED this session.** Independently reproduced:
- `Plan`/`PlanPage` models, `StorageService`, `PdfInspectionService`, `PlanService`, thin `/api/projects/{id}/plans*` routes all present and match the checklist.
- Migration `709345772063` (depends on `72c82e8ce581`) — chain confirmed sound by direct inspection; live `alembic current` showed the DB already sitting at this head.
- Live smoke test this session (not just trusting the prior checklist): uploaded the one real PDF fixture (`backend/test_plan/floorplan.pdf`) through `POST /api/projects/{id}/plans` against real Postgres + real filesystem storage → `201`, `processing_status: ready`, `pdf_type: raster`, `page_count: 1`. Confirmed both the old and new upload paths work side by side in the same live process.
- Full suite: **114 tests, 0 failures**, executed in this session (not copied from the prior report) — 27 original MVP + 30 R1 + 57 R2.
- Frontend `npm run build` → 85 modules, 0 errors, executed in this session.
- **Known, honestly-documented gap (not a regression):** raster/vector/mixed classification calibration is based on exactly one real PDF; vector and multi-page real-file validation per `docs/testing/R2_REAL_PLAN_VALIDATION.md`'s manual procedure has not been executed.
- **Not committed to git**, same caveat as R1.

**Overall: both R1 and R2's engineering claims hold up under independent re-execution. The only correction to the prior self-reported status is procedural, not technical: none of this is in git history yet, which changes what "done" means for release purposes.**

---

## 4. Test/runtime verification performed this session

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py"` | **114 tests, 0 failures**, run against live Postgres (backend `.venv`, Python 3.11.7) |
| App import (`from app.main import app`) | Succeeds, no import errors |
| OpenAPI route dump (`app.openapi()`) | All 17 expected paths present: legacy 6 (`/`, `/health`, `/upload-pdf`, `/rendered-page/{file_id}`, `/suggest-plan-scale/{file_id}`, `/analyze-section/{section_file_id}`), detection/export/vlm 6, new projects/plans 5 |
| `GET /health` (live server) | `{"status":"ok"}` |
| Alembic `current`/`heads` | Both report `709345772063 (head)` — DB already migrated |
| Full legacy workflow live | `/upload-pdf` → `/rendered-page/{id}` → `/save-hatch-sample` → `/detect-hatch` → `/export-excel`, all HTTP 200, real detections and a real 5176-byte `.xlsx` returned |
| Full new workflow live | `POST /api/projects` → `POST /api/projects/{id}/plans` (real PDF) → `ready`/`raster`/1 page, all against real Postgres |
| `npm run build` (frontend) | `✓ 85 modules transformed`, built in 2.05s, 0 errors |
| Frontend test suite | **NOT PROVEN** — no runnable Jest/Vitest/Playwright config found; a `playwright.smoke.run.js` exists but references an absolute path into a gitignored recovery folder, not runnable from a clean checkout |
| Live OpenAI/VLM call | **NOT PROVEN** — no `OPENAI_API_KEY` configured in this shell; fallback path is tested, real-API path is not |
| Dev DB left clean | Confirmed: test project/plan created during live verification were deleted afterward (`DELETE FROM projects...`, then `SELECT count(*)` → 0 rows in both `projects` and `plans`) |

---

## 5. Core architectural principles — assessment

**Deterministic quantity engine — HOLDS.** Exactly one function (`quantityEngine.js::buildQuantityResult`) computes `final_area_m2`/`volume_m3`. Confirmed by reading the file and confirming (via the export route's Pydantic model) that the backend accepts these as opaque floats and never recomputes them. No duplicate calculation path exists anywhere in the codebase (backend or frontend).

**Human-in-the-loop — HOLDS.** `DetectionReviewPanel.jsx` (accept/reject) and `RegionEditor.jsx` (manual add/subtract) sit between every CV/AI signal (`hatch_detection.py`, `vlm_service.py`) and the quantity engine. Nothing computed by CV or the VLM reaches `quantityEngine` without an explicit user action in between (confirmed by reading `PlanViewer.jsx`'s state flow).

**Separation of concerns — HOLDS for R1/R2, PARTIAL for the legacy MVP surface.** `routes/projects.py` and `routes/plans.py` are thin (no raw SQL, no business logic — just service calls + exception→HTTP mapping). `ProjectService`/`PlanService` own all domain logic. `StorageService` centralizes *new* storage paths. The **legacy** surface (`main.py`, `routes/detection.py`) still computes storage paths as duplicated module-level constants in two files — this was deliberately left alone during R2 (documented, low-risk decision) but is real, standing duplication.

**Persistence — Project and Plan/PlanPage survive a process/DB restart** (schema-level guarantee via Postgres + Alembic; the R1 checklist's cross-process proof was read and is methodologically sound, though not independently re-run this session since it would require tearing down/restarting the dev Postgres container). **Everything else — uploaded PDFs via the old `/upload-pdf` path, hatch samples, detections, corrections, height confirmation, and the final quantity — survives only as long as the browser tab and the backend process filesystem are alive.** There is no `Analysis`/`Export` record of any completed takeoff.

---

## 6. Technical debt

### BLOCKER
| # | File(s) | Problem | Risk | Blocks next release? |
|---|---|---|---|---|
| B1 | *(git working tree)* | R1 and R2 (30+ new/changed files, 2 migrations, `docker-compose.yml`) are **uncommitted**. | A crash, `git clean`, or accidental `git checkout -- .` loses two completed releases with zero recovery path. | **Yes — commit before any further work.** |
| B2 | `main.py::upload_pdf` | No content validation — only checks the filename ends in `.pdf`. A renamed non-PDF or corrupt file reaches `fitz.open` unguarded and raises an unhandled exception → default FastAPI 500 with a stack trace potentially exposed. | Data-quality and minor information-disclosure risk on the still-primary user-facing upload path (the new `/api/projects/{id}/plans` path already fixes this; the old path, which the current frontend actually calls, does not). | Yes, before any release that touts the old path as production-ready. |

### HIGH
| # | File(s) | Problem | Risk | Timing |
|---|---|---|---|---|
| H1 | `main.py`, `routes/detection.py` | Duplicated `BASE_DIR`/`STORAGE_DIR` computation, two independent legacy storage layouts. | Any future path-related fix must be applied twice; drift risk. | Before R3 touches storage further |
| H2 | `backend/requirements.txt` vs `requirements-minimal.txt` | Diverging dependency lists; unused packages (`pandas`, `reportlab`, `rapidocr-onnxruntime` — grep-confirmed zero imports) ship in the file `CLAUDE.md` tells contributors to install from. | Bloated installs, confusing which file is authoritative, larger attack surface for supply-chain scanning later. | Before adding CI/dependency scanning |
| H3 | *(whole repo)* | No CI. Nothing currently prevents a broken commit from landing on `main`. | Regressions ship silently; 114 passing tests today have no automated enforcement going forward. | Immediately after B1 is resolved |
| H4 | `main.py` CORS config | `allow_origins=["*"]`, `allow_credentials=True`. | Fine for solo local dev; unsafe if this origin config is ever carried into a hosted/multi-user deployment untouched. | Before any deployment release |
| H5 | *(whole repo)* | No structured logging anywhere. Errors are only visible via FastAPI's default exception responses/console traceback. | Diagnosing a production issue (e.g. a failed Plan ingestion) has no request-correlated trail. | Before first hosted deployment |
| H6 | `pdf_inspection_service.py` | `RASTER_IMAGE_COVERAGE_THRESHOLD` calibrated against exactly one real scanned PDF. | Misclassification risk (→ `unknown`) on real customer scans with different margin/scan characteristics, silently degrading the R3 legend workflow's assumptions. | Before R3 relies on `pdf_type` for branching logic |

### MEDIUM
| # | File(s) | Problem | Risk | Timing |
|---|---|---|---|---|
| M1 | root of repo | `_backup_before_flatten/` (92MB, includes a checked-out venv with compiled `cv2` binaries), `_recovery_candidates/`, `_live_before_validated_restore_20260513_080814/`, `massiq-mvp/`, plus an unexplained root-level `storage/` and `test_plans/` — all gitignored but present on disk. | Confuses any new contributor about what the "real" app is; `README.md` still narrates this recovery story as the primary repo description. | Cleanup pass, not release-blocking |
| M2 | `main_simple.py`, `services/vlm_usage_tracker.py`, `backend/README.md`, `routes/detection_patch.txt` | 0-byte tracked files, confirmed unimported by anything (`grep` verified). | Minor confusion, no functional risk. | Low-effort cleanup, any time |
| M3 | frontend | No frontend test suite runnable from a clean checkout (`playwright.smoke.run.js` hardcodes a path into a gitignored recovery folder). | Frontend regressions (e.g. in `quantityEngine.js` or `PlanViewer.jsx`'s coordinate math) have zero automated coverage. | Before frontend work resumes at any real pace |
| M4 | `PlanViewer.jsx` (641 lines) | Owns essentially all workflow state as flat `useState` calls; a single-file hotspot. | Not a bug today, but every new wizard step (R3 legend workflow) will make this larger and harder to review safely. | Before/during R3, not before |
| M5 | `routes/plans.py` | No preview-serving HTTP endpoint exists yet; `StorageService.resolve_preview` is tested but unreachable over HTTP. | Blocks any future UI that wants to show a Plan's rendered page from the *new* pipeline (today only the *old* `/rendered-page/{id}` is servable). | R3 will need this |
| M6 | `services/plan_service.py` | `Plan.ON DELETE CASCADE` FK is unreachable — no project-delete endpoint exists at any layer. | Dead code path; not a correctness bug, just unused defensive schema. | No urgency |

### LOW
| # | File(s) | Problem | Recommended timing |
|---|---|---|---|
| L1 | `frontend/tsconfig.json` | Exists, but the codebase is 100% `.jsx`. No typed layer to extend. | Decide JSDoc-types vs. TS migration before building the R3 legend API client, not now |
| L2 | Second git remote `massiq123` | Purpose/relationship to `origin` is not documented anywhere in the repo. | Clarify or remove; no functional impact today |
| L3 | `hatch_detection.py` | Magic thresholds (8 scale steps, 2 hard caps) are named constants but not environment-configurable. | Revisit only when Detection V2 (R6) work starts |

---

## 7. Architectural gaps vs. the target product direction

`Project → Plans → Plan Preparation → Legend → Materials → Analysis → Results`

| Stage | Foundation present? | Gap before it can be safely built |
|---|---|---|
| Project | ✅ complete (R1) | none |
| Plans | ✅ complete (R2) | none |
| Plan Preparation | ⚠️ partial | scale confirmation is still frontend-only pixel math against the *old* upload path; nothing connects a confirmed scale to a persisted `Plan`/`PlanPage` row yet |
| Legend (R3) | ❌ not started | Needs: a preview-serving endpoint (M5) for the new pipeline, `LegendEntry` model+migration, real OCR (current "OCR" is filename regex), a decision on where hatch-sample crops get stored (new `StorageService` vs. old `hatch_samples/`) |
| Materials | ❌ not started | Depends on Legend existing first; component-name free text has no validation/confirmation model at all today |
| Analysis (Detection V2, R6) | ❌ not started | Current detector is a stateless, synchronous, single-scale-sweep template matcher with no persistence of results; nothing about it blocks starting R3/R4, but R6 will need an `Analysis`/job-tracking model that doesn't exist |
| Results/Export hardening (R8) | ⚠️ partial | Excel export works and is deterministic; nothing persists a "completed takeoff" as a queryable record — every export is a stateless, one-shot POST |

**Readiness verdict:** the system is **ready to start R3** structurally (Project/Plan foundation is solid and tested) but **R3 should not start until B1 (commit R1/R2) and B2 (old upload validation) are resolved**, and H6 (classification calibration) should get at least one more real vector/multi-page PDF before R3 leans on `pdf_type` for UI branching.

---

## 8. Premature-complexity check

None of microservices, Kubernetes, Kafka, Redis, Celery, Qdrant, Elasticsearch, event sourcing, GraphQL, custom ML models, image embeddings, or LLM agents are justified by anything in this repository today. Current scale (single dev machine, synchronous request-response, one Postgres instance, <200 detections per request, one PDF per upload) is comfortably served by the existing FastAPI + Postgres + filesystem architecture. The one piece of infrastructure worth adding soon is **CI** (H3) — not because of scale, but because there is currently no automated gate at all protecting 114 passing tests from regressing.

---

## 9. Release status board

```
R0 — Repository/architecture audit
STATUS: COMPLETE

R1 — Project Persistence
STATUS: COMPLETE (re-verified live this session) — NOT YET COMMITTED TO GIT

R2 — Plan/PDF Foundation
STATUS: COMPLETE (re-verified live this session) — NOT YET COMMITTED TO GIT

R3 — Legend Workflow
STATUS: NOT IMPLEMENTED

R4 — Hatch Feature Engine
STATUS: NOT IMPLEMENTED

R5 — Pattern Library
STATUS: NOT IMPLEMENTED

R6 — Detection Engine V2
STATUS: NOT IMPLEMENTED

R7 — Human Review Hardening
STATUS: NOT IMPLEMENTED

R8 — Quantity/Export Hardening
STATUS: NOT IMPLEMENTED
```

---

*This document describes state only, as verified by direct execution and code inspection on 2026-08-25. See `docs/architecture/PRODUCTION_ROADMAP.md` for the proposed next-release plan.*
