# MassIQ — Production Roadmap

Companion to `docs/architecture/CURRENT_IMPLEMENTATION_STATUS.md`. That document says what exists; this one says what to build next, in what order, and why. Nothing in this document has been implemented — it is a proposal pending approval.

---

## Guiding constraint from the audit

R1 and R2 are functionally complete and independently re-verified (114/114 tests, live Postgres, live HTTP smoke tests, clean `alembic` up/down chain), but **exist only in the working tree**. Every recommendation below is sequenced around one fact: *the next release is not a feature release.*

---

## Recommended release sequence

### Release "R1+R2 Landing" (release the audit's findings, not a feature)

**Objective:** Get the already-built, already-tested R1+R2 work safely into git history with a working CI gate, and close the two BLOCKER items, before any new feature work starts.

**Why now:** Two completed, tested releases currently have no durable existence beyond this machine's working tree. This is the single highest-leverage, lowest-risk action available — it captures ~90 files of verified work and removes the single biggest risk in the whole audit (B1).

**In scope:**
- Commit R1 (`Project` model/service/routes/tests/migration) and R2 (`Plan`/`PlanPage`/`StorageService`/`PdfInspectionService`/`PlanService`/routes/tests/migration) to `main`, in that order, as two separate commits (or a short-lived branch + PR if the team wants review history).
- Fix B2: add the same `open_and_validate`-style magic-byte + PyMuPDF-open check to the **old** `/upload-pdf` route, returning 400 instead of an unhandled 500 on invalid input. Minimal, additive, does not change the route's response shape on the happy path.
- Add a minimal GitHub Actions CI workflow: checkout → set up Python 3.11 + Node → `pip install -r backend/requirements.txt` → spin up Postgres service container → `alembic upgrade head` → `python -m unittest discover` → `npm ci && npm run build` in `frontend/`. No linting/formatting gate yet (that's a later, separate decision — see Production-Engineering section).
- Reconcile `requirements.txt`/`requirements-minimal.txt` (H2): pick one file as authoritative (recommend keeping `requirements.txt`, deleting the unused `pandas`/`reportlab`/`rapidocr-onnxruntime` lines from it since grep confirms zero imports), delete or clearly mark `requirements-minimal.txt` as deprecated.

**Explicitly out of scope:** any new model, any new route, any frontend change, Legend/OCR/Detection V2, deleting the root clutter directories (M1 — separate low-risk cleanup, not bundled here to keep this release's diff auditable).

**Files/modules likely affected:** `backend/app/main.py` (upload validation only), `backend/requirements.txt`, `backend/requirements-minimal.txt`, new `.github/workflows/ci.yml`, plus `git add` of everything currently untracked under `backend/app/{core,db,models,routes/plans.py,routes/projects.py,schemas,services/pdf_inspection_service.py,services/plan_service.py,services/project_service.py,services/storage_service.py}`, `backend/tests/*`, `backend/alembic*`, `docker-compose.yml`, `docs/*`.

**Tests required:** full existing 114-test suite must stay green; add 2–3 new tests for the `/upload-pdf` validation fix (invalid/corrupt/fake-PDF → 400, matching the pattern already proven in `test_pdf_inspection_service.py`).

**Regression surfaces:** the old MVP workflow end-to-end (upload → render → hatch sample → detect → export) — re-run the live smoke sequence from this audit after the validation fix lands, since it's the one behavioral change in this release.

**Definition of Done:** `git log` shows R1+R2 as real commits on `main`; CI is green on a fresh clone with no local state; `/upload-pdf` returns 400 (not 500) for a non-PDF or corrupt file; `requirements.txt` contains only packages actually imported somewhere in `backend/app`.

**Release gate:** CI green + the live smoke sequence (old workflow + new project/plan workflow) both pass on a clean checkout, exactly as reproduced in this audit.

**Main risks:** low. This release adds no new business logic; the main risk is merge/commit hygiene (accidentally committing `__pycache__`, `.venv`, or local `.env` — verify `.gitignore` coverage before `git add`).

---

### Release R3 — Legend Workflow (first real feature release, next after landing)

**Objective:** Select a hatch pattern → select its legend description → OCR-assisted read → user correction → material confirmation → persist as a `LegendEntry` tied to a `Plan`.

**Why now:** It's the next stage in the product direction and the only one whose foundation (Project/Plan persistence, PDF classification, storage abstraction) is now actually ready, per this audit's gap analysis.

**In scope:** `LegendEntry` model + migration; a real OCR call (not filename regex) scoped to a user-drawn legend crop; a preview-serving HTTP endpoint for the new Plan pipeline (closes M5, a hard prerequisite — the UI needs to show the plan to draw a legend box on it); `LegendService`; thin `/api/projects/{id}/plans/{id}/legend-entries` routes; frontend legend step wired to the new endpoints (can run alongside, not replacing, the existing hatch-sample flow initially).

**Explicitly out of scope:** hatch feature extraction/embeddings (R4), any pattern library (R5), changing the existing `/detect-hatch` detector, changing `quantityEngine.js`.

**Files/modules likely affected:** new `backend/app/models/legend_entry.py`, new migration, new `backend/app/services/legend_service.py`, new `backend/app/services/ocr_service.py`, new route file, `frontend/src/components/LegendAssistantPanel.jsx` (extend, don't rewrite).

**Tests required:** OCR service unit tests with a fallback contract mirroring `vlm_service.py`'s proven pattern (never raise, always return a valid empty shape); route/service tests mirroring the R1/R2 test structure; at least one real (non-synthetic) legend crop tested manually per a documented procedure, same spirit as `docs/testing/R2_REAL_PLAN_VALIDATION.md`.

**Regression surfaces:** the whole R1/R2 chain (project/plan CRUD must stay green); the old MVP hatch-sample flow, since the legend UI will sit visually near it.

**Definition of Done:** a user can draw a legend region on a *persisted* Plan's preview, get an OCR-suggested description, correct it, confirm a material, and see a `LegendEntry` row survive a backend restart.

**Release gate:** full regression suite green; live smoke test of the new legend flow against a real Plan.

**Main risks:** OCR accuracy on real construction-drawing legends is unproven in this codebase (no OCR library is currently used anywhere — `rapidocr-onnxruntime` is an unused dependency today); budget time for a calibration pass similar to R2's raster-threshold finding.

---

### R4 — Hatch Feature Engine, R5 — Pattern Library, R6 — Detection Engine V2, R7 — Human Review Hardening, R8 — Quantity/Export Hardening

Not detailed here — each depends on R3 landing first, and per the audit's own instruction ("do not blindly continue old plans," "minimal scope per release"), their concrete scope should be re-derived from the codebase state *after* R3 ships, not pre-committed now. The one standing architectural note for all of them: **do not introduce a background job queue (Celery/etc.) until a specific release's payload/latency requirement actually demands it** — nothing in R3–R5's expected scope (OCR on a small crop, a library CRUD) needs it; R6 (Detection V2, if it becomes computationally heavier — e.g. tiled scanning across a full large plan) is the first plausible candidate to revisit that question, and only with evidence from real latency numbers at that time.

---

## Production-engineering standards — when each becomes appropriate

| Practice | Recommendation |
|---|---|
| CI pipeline | **Now** (bundled into the "R1+R2 Landing" release above) — this is the one non-negotiable gap given 114 tests already exist with zero automated enforcement |
| Linting/formatting policy | After CI exists and is green; add `ruff`/`black` (Python) and `eslint`/`prettier` (frontend) as a fast-follow, non-blocking-at-first CI job so it doesn't stall R3 |
| Typing/static analysis | Defer. `mypy`/TS migration is a bigger investment; revisit when the R3 API client is being built (L1) |
| Unit testing | Already in good shape (114 tests) — keep the existing per-service `unittest` pattern for R3+, don't switch frameworks mid-stream |
| Integration/E2E testing | Add a real Playwright suite (fixing M3's broken hardcoded-path script) once R3's frontend flow exists — testing the legend workflow end-to-end is a better first E2E target than retrofitting one for the already-stable legacy flow |
| Migration testing | Already present as a manual practice (up/down/up cycles, documented in the checklists) — worth adding as an automated CI step (`alembic upgrade head && alembic downgrade -1 && alembic upgrade head`) in the same CI pipeline |
| Pre-commit hooks | Defer until linting/formatting policy is decided; don't add hooks for tools that aren't adopted yet |
| Structured logging | Add when the first hosted/shared deployment is planned (H5) — not needed for continued local-dev feature work, but should land no later than the release that first exposes MassIQ outside one developer's machine |
| Request IDs / error contracts | Same timing as structured logging — bundle together |
| Configuration validation | Partially present (`pydantic-settings`); extend as new required env vars appear (e.g. an OCR API key for R3), no new mechanism needed |
| Secrets handling | `.env` is gitignored, `.env.example` documents required vars — adequate for current single-dev-machine scope; revisit before any hosted deployment |
| Backup/restore strategy | Defer until real user data exists beyond dev/test — trivial today (a fresh `alembic upgrade head` recreates schema, no data to lose yet) |
| Database constraints | Already reasonably strong (FKs with `ON DELETE CASCADE`, unique constraint on `(plan_id, page_number)`, `NOT NULL` where appropriate) — maintain this bar for every new R3+ table |
| API versioning | Defer — no external consumers yet; revisit only if a public/partner API surface is ever planned |
| Release notes / semantic versioning | Start lightweight release notes now (one line per release in a `CHANGELOG.md`), given multiple releases are about to land in quick succession; full semver is unnecessary complexity for a single-deployable app with no external package consumers |
| Observability (metrics/tracing) | Defer until hosted deployment; structured logging is the correct first step, not a metrics stack |
| Dependency locking | Add a `requirements.lock` (via `pip-compile` or similar) or move to `poetry`/`uv` **after** the H2 reconciliation lands — locking a file that's still internally inconsistent just locks in the inconsistency |
| Security scanning | Add `pip-audit`/`npm audit` as a non-blocking CI job once CI exists — cheap, no reason to defer once the pipeline is there |
| Build reproducibility | Already reasonable (`requirements.txt` + `package-lock.json` both present) — no action needed beyond H2 |

---

## Current system map

```
Frontend (React 18 + Vite, no router)
  App.jsx
   └── UploadPanel.jsx
        └── PlanViewer.jsx (641 lines, owns all workflow state)
             ├── LegendAssistantPanel.jsx
             ├── HatchDetectionPanel.jsx
             ├── DetectionReviewPanel.jsx
             ├── RegionEditor.jsx
             ├── SectionHeightPanel.jsx
             └── ExportButton.jsx
  utils/quantityEngine.js  (sole deterministic area/volume formula)
        ↓ axios, 120s timeout
FastAPI (backend/app/main.py)
  ├── Legacy MVP surface (no DB)
  │     main.py: /upload-pdf, /rendered-page/{id}, /suggest-plan-scale/{id}, /analyze-section/{id}
  │     routes/detection.py: /save-hatch-sample, /detect-hatch  → services/hatch_detection.py
  │     routes/export.py:    /export-excel                      → services/excel_service.py
  │     routes/vlm.py:       /vlm/*                              → services/vlm_service.py (OpenAI, graceful fallback)
  └── R1/R2 surface (Postgres-backed)
        routes/projects.py → services/project_service.py → models/project.py
        routes/plans.py    → services/plan_service.py    → models/plan.py, models/plan_page.py
                                   ├─ services/pdf_inspection_service.py (vector/raster/mixed classification)
                                   └─ services/storage_service.py (plans/<uuid>/original.pdf, pages/000N.png)
        ↓
   PostgreSQL 16 (docker-compose, host port 5433) via SQLAlchemy + Alembic
```

## Target architecture, next 2–3 releases (through R3)

```
Frontend
  App.jsx
   └── PlanViewer.jsx  (progressively split as R3 grows it — not rewritten wholesale)
        ├── ...existing panels unchanged...
        └── LegendWorkflowPanel.jsx (new, R3)
  utils/quantityEngine.js  (unchanged — still the only calculation authority)
        ↓
FastAPI
  ├── Legacy MVP surface (unchanged, now with input-validation parity — R1+R2 Landing)
  └── Postgres-backed surface
        routes/projects.py, routes/plans.py  (unchanged)
        routes/legend_entries.py (new, R3) → services/legend_service.py → models/legend_entry.py
                                                    └─ services/ocr_service.py (new, R3 — real OCR, graceful-fallback pattern reused from vlm_service.py)
        ↓
   PostgreSQL 16 (projects, plans, plan_pages, legend_entries)
   Filesystem (storage/plans/<uuid>/{original.pdf, pages/, legend-crops/})
  + CI (GitHub Actions): tests, migration up/down, frontend build — new, R1+R2 Landing
```

No new infrastructure category (queue, cache, search engine, vector DB) appears in this 2–3 release horizon — consistent with Section 8 of the companion status document.

---

## Final recommendation

**Current stable baseline:** the legacy MVP workflow (upload → scale → hatch sample → detect → review/correct → confirm height → export) works end-to-end today, live-verified in this audit, with a genuinely deterministic, single-source-of-truth quantity calculation and real human-in-the-loop review. R1 (Project persistence) and R2 (Plan/PDF ingestion with classification) are also fully built and passing 114 tests, live-verified against real Postgres — but exist only in the working tree, not in git history.

**What should NOT be touched yet:** `hatch_detection.py`'s detection algorithm, `excel_service.py`'s payload contract, `quantityEngine.js`, the old MVP route names/shapes, and the R1/R2 model/service structure itself — all are working and tested; touch them only with a documented migration reason, not as part of landing or cleanup work.

**Immediate next release:** "R1+R2 Landing" (commit the existing work, add CI, fix the old-upload validation gap, reconcile the two requirements files). Exactly this, nothing else.

**Why this is correct:** it is the only release that converts already-verified, already-working engineering effort into something that can't be lost to a bad `git clean`, and it closes the audit's only two BLOCKER items before any new feature surface increases the codebase's size and risk further.

**What to do after that release:** R3 — Legend Workflow, scoped as above, starting with the preview-serving endpoint it structurally requires.

**Biggest engineering risk right now:** B1 — two completed, tested releases sitting uncommitted in a working tree with no CI and no branch protection. This is a process risk, not a code-quality risk, and it is fully within this team's control to close immediately.

**Biggest product risk right now:** the vector/raster/mixed PDF classifier (which R3+ will start depending on for UI branching) has been calibrated against exactly one real scanned floor plan. If real customer plans vary more than that one sample in scan quality/margins, R3's legend workflow could inherit silent misclassification. Recommend gathering a small set (3–5) of real, varied construction PDFs before R3's classification-dependent UI decisions are finalized.

**Recommended Claude/Codex workflow:** implementation and review should remain separated by evidence, not by which model does which role — whoever implements a release should not be the sole verifier of its Definition of Done; the pattern already used for R1/R2 (a checklist with live-executed evidence, re-verified independently in this audit) is the right bar to keep. Concretely: one pass implements against the Definition of Done in this document; a second, independent pass re-runs the full test suite plus the specific live smoke sequence for that release before it's considered mergeable — exactly as this audit re-verified R1/R2 rather than trusting the original checklists at face value. Approval gates stay evidence-based (tests pass, live smoke test reproduced, migration up/down cycle proven) regardless of which model or person performed which step.
