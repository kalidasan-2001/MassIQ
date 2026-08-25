# R2.5 — Foundation Hardening & Release Hygiene: Checklist

Date: 2026-08-25
Repository: `C:\Users\kalid\MassIQ`, branch `release/r1-r2-foundation` (created from `main` at commit `192c4fd`)
Scope: convert the already-verified R1/R2 foundation into a safely versioned, CI-protected baseline. No R3 domain models or features were introduced (see "Do not implement" list at the end).

Status legend: **PASS** (executed with evidence), **FAIL**, **BLOCKED**, **DEFERRED** (explicitly out of scope for this release, documented for later).

---

## 1. R1/R2 checkpoint committed

**PASS.** Branch `release/r1-r2-foundation` created from `main`. All verified R1/R2 files staged and inspected (`git diff --cached --stat`, `git diff --cached --check`, filename inspection for secrets) before commit. Committed as a single checkpoint, `feat(core): establish persistent project and plan foundation` (commit `e89ea12`).

**Single-commit decision (not split into R1/R2 commits):** `backend/alembic/env.py` unconditionally imports `plan`, `plan_page`, and `project` together, and `backend/app/main.py`'s router-registration diff already registers both `projects` and `plans` routers in one pre-existing change. Splitting into two commits would require temporarily rewriting those already-verified files just for history cosmetics, and risks an intermediate commit that fails to import. Per the R2.5 instructions ("do not artificially split changes if doing so creates risk... the priority is a reproducible clean checkpoint"), a single combined commit was used instead.

## 2. No secrets/private files committed

**PASS.** Verified before commit:
- `git diff --cached --name-only | grep -iE "\.env$|secret|storage/uploads|storage/plans|\.pdf$|_backup|_recovery|_live_before"` → no matches.
- `backend/.env` (real, gitignored) confirmed absent from the staged list; only `backend/.env.example` (template, no real values) was staged.
- No file under `backend/app/storage/`, no root-level recovery snapshot (`_backup_before_flatten/`, `_recovery_candidates/`, `_live_before_validated_restore*/`, `massiq-mvp/`), no `.venv/`, no `*.pdf` was staged.
- `docker-compose.yml`'s Postgres credentials (`massiq`/`massiq`) are a fully local, throwaway dev-only container — not a real secret.

## 3. Legacy PDF validation

**PASS.** `backend/app/main.py::upload_pdf` now reads the upload into memory and calls `PdfInspectionService.open_and_validate(content)` **before** writing anything to disk — the exact same tested validation R2's Plan pipeline uses (magic-byte check, PyMuPDF open, page-0 readability). No second validation implementation was written. `InvalidPdfError` maps to a clean `HTTPException(400, ...)`.

## 4. Corrupt PDF behavior

**PASS.** Live: `curl -F "file=@fake.pdf" .../upload-pdf` with non-PDF content → `HTTP 400`, `{"detail":"File does not start with a PDF header (%PDF-)"}` (previously would have reached `fitz.open` unguarded). Test: `test_legacy_upload_pdf.py::test_corrupt_pdf_returns_400_not_500` — 400, no `Traceback` substring in the response body, zero new files on disk.

## 5. Fake PDF behavior

**PASS.** `test_legacy_upload_pdf.py::test_fake_text_file_renamed_pdf_returns_400_not_500` — a plain-text file renamed `.pdf` → 400, no orphan files. Also covered: empty file (`test_empty_file_returns_400_not_500`) and the pre-existing filename-extension check (`test_non_pdf_extension_still_rejected_before_touching_content`), confirming the hardening is additive, not a replacement.

## 6. Valid legacy upload regression

**PASS.** `test_legacy_upload_pdf.py::test_valid_pdf_upload_still_succeeds` — a real synthetic PDF still returns 200 with the unchanged response shape (`file_id`, `page_image_url`, `width`, `height`), and the rendered page is actually servable afterward. Live: uploaded the one real PDF fixture (`test_plan/floorplan.pdf`) through the running server → 200, `/rendered-page/{id}` → 200.

## 7. CI added

**PASS.** `.github/workflows/ci.yml` added: two jobs, `backend` (checkout → Python 3.11 → `pip install -r backend/requirements.txt` → Postgres 16 service container → `alembic upgrade head` → `python -m unittest discover -s tests -p "test_*.py"`) and `frontend` (checkout → Node 20 → `npm ci` → `npm run build`). No deployment, no Docker image publishing, no Kubernetes, no linting/type-checking gate (deferred, see below).

## 8. Backend CI commands verified locally

**PASS.** Simulated the CI backend job against a genuinely fresh Postgres instance (not the pre-migrated dev DB), to prove the workflow will pass on a clean checkout rather than trusting YAML syntax alone:
- Started an ephemeral `postgres:16-alpine` container (`ci-check-postgres`, host port 5434, empty database).
- `alembic upgrade head` against it → ran both migrations from `None` cleanly: `-> 72c82e8ce581 -> 709345772063`. `\dt` confirmed all 4 expected tables (`alembic_version`, `plan_pages`, `plans`, `projects`).
- `python -m unittest discover -s tests -p "test_*.py"` against the same fresh instance → **125 tests, 0 failures**.
- Ephemeral container removed afterward (`docker rm -f ci-check-postgres`); the developer's regular `massiq-postgres` dev container was untouched throughout.

## 9. Frontend CI commands verified locally

**PASS.** `npm ci` (clean, lockfile-only install, matching what CI runs — not `npm install`) → succeeded, 80 packages. `npm run build` → `✓ 85 modules transformed`, 0 errors. (`npm audit` reported 7 pre-existing vulnerabilities in transitive dependencies — 1 low, 1 moderate, 5 high; not remediated in this release per the explicit instruction not to perform dependency cleanup here, but recorded under Deferred Technical Debt below since it's new information from this session.)

## 10. Classifier validation result

**PASS (raster), INSUFFICIENT CALIBRATION DATA (vector, multi-page).** Full findings in `docs/testing/R2_REAL_PLAN_VALIDATION.md`'s new "R2.5 calibration check" section. Summary: searched all 31 PDFs accumulated in `backend/app/storage/uploads/` for any real construction plan beyond the one already-documented raster scan. Found none — the only other real (non-synthetic) PDF present is a 2-page PDF rendering of one of MassIQ's own quantity-report exports (not a construction drawing), plus trivial test-sized PDFs from routine manual testing. `RASTER_IMAGE_COVERAGE_THRESHOLD`/`MIXED_IMAGE_COVERAGE_THRESHOLD` were **not changed** — no tuning was performed to force a pass, and the one genuine real plan (`floorplan.pdf`) still classifies correctly (`image_coverage_ratio=0.5796` → `RASTER`) under the existing threshold. **R3 must treat `pdf_type` as advisory metadata, not a hard business-rule branch, until real vector/multi-page evidence is available.**

## 11. Preview endpoint decision/result

**IMPLEMENTED.** `GET /api/projects/{project_id}/plans/{plan_id}/pages/{page_number}/preview` was small and independently testable, so it was built in R2.5 rather than deferred to R3. Implementation: `PlanService.get_page()` (new) reuses `get_plan()`'s existing project/plan ownership and isolation check, then looks up the `PlanPage` by `page_number`; the route resolves the file via `StorageService.resolve_preview()` using only the DB-stored `preview_reference` (never client input) and returns bytes via `FileResponse` with `media_type="image/png"` and a synthetic filename (`page-N.png` — the real storage path is never exposed). 404 for unknown project, unknown plan, unknown page, and cross-project access (all reusing `get_plan`'s existing isolation guarantee). Live-verified against a running server in addition to the automated tests below.

## 12. Full test result

**PASS.** `python -m unittest discover -s tests -p "test_*.py"` → **125 tests, 0 failures** (114 pre-existing baseline + 5 new `test_legacy_upload_pdf.py` + 6 new preview-endpoint tests in `test_plan_routes.py`). Exceeds the required "at least 114 plus new tests, all passing."

## 13. Frontend build result

**PASS.** `npm run build` → `✓ 85 modules transformed`, built in ~2s, 0 errors. Frontend source was not modified in R2.5 (module count unchanged from the R1/R2 baseline).

## 14. Legacy workflow regression result

**PASS.** Live, against a running server, after all R2.5 code changes: `/upload-pdf` (valid PDF → 200, invalid → 400) → `/rendered-page/{file_id}` (200) → `/save-hatch-sample` (200) → `/detect-hatch` (200, real detections) → `/export-excel` (200, real 5176-byte `.xlsx`). No regression.

---

## Legacy storage duplication (Section 5) — result

**DONE, small and behavior-preserving.** `main.py`, `routes/detection.py`, and `routes/vlm.py` (a third duplication site found during this release, not previously flagged) each independently recomputed identical `BASE_DIR`/`STORAGE_DIR`/etc. constants. Extracted into a new `backend/app/storage_paths.py` module (directory layout, filenames, and creation timing all unchanged — a pure duplication removal, not a storage migration). All three call sites now import from it. Full regression suite re-run afterward: 119/119 passing at that point (before the preview-endpoint tests were added), confirming byte-for-byte behavioral equivalence. `services/storage_service.py` (the *new* R2 Plan-pipeline abstraction) was not touched or merged with this — doing so would have broadened scope into the storage migration explicitly deferred to R3 preparation.

## Dependency file decision (Section 7)

**`backend/requirements.txt` is authoritative.** It is the file `CLAUDE.md`'s setup instructions reference, the only file R1 added its four new dependencies (`sqlalchemy`, `alembic`, `psycopg2-binary`, `pydantic-settings`) to, and the file CI now installs from. `backend/requirements-minimal.txt` is **not** installed by CI and is recorded as deferred technical debt (divergent, contains fewer/different packages) — no packages were removed from either file in this release, per the explicit instruction not to perform an uncontrolled dependency cleanup.

## Frontend test foundation (Section 10) — decision only, not implemented

**Recommendation for R3: Vitest + React Testing Library.** Reasoning: Vite is already the build tool (Vitest shares its config/transform pipeline with zero extra bundler setup), and RTL is the standard pairing for React 18 component/behavior tests. No frontend testing stack was added in R2.5 (not required by the upload-validation change, which is entirely backend). **Priority order for whichever tests get written first in R3:**
1. `utils/quantityEngine.js` — the sole deterministic area/volume formula; highest-value target since it's the one calculation the whole app's correctness guarantee rests on.
2. Manual add/subtract correction math (`RegionEditor.jsx`'s output feeding `quantityEngine`) — second-highest value, directly adjacent to #1.
3. Workflow state transitions in `PlanViewer.jsx` (the step-wizard gating logic) — lower priority, more refactor-sensitive; better done after/alongside any R3 restructuring of that file rather than before.
`PlanViewer.jsx` was **not** refactored in R2.5, per instruction.

## Structured logging (Section 11) — deferred

**DEFERRED**, as instructed. Not required for R2.5: the new upload-validation path returns clear, testable 4xx responses without needing a logging framework to debug. Recorded for a later hardening release, timed to land no later than the release that first exposes MassIQ outside one developer's machine (matches `PRODUCTION_ROADMAP.md`'s existing recommendation).

## CORS (Section 12) — not changed

**DEFERRED**, as instructed. `main.py`'s `allow_origins=["*"], allow_credentials=True` is unchanged. Recorded: **CORS hardening required before hosted/multi-user deployment.**

## .gitignore review (Section 16)

**PASS, no changes needed.** Reviewed against the checklist: `.env`/`*.env` ignored (but not `.env.example`, which was correctly committable and committed); `backend/app/storage/`, `storage/`, `exports/` ignored; `.venv/`/`venv/` ignored; `*.pdf` ignored everywhere (protects private test plans regardless of directory name, confirmed via `git check-ignore -v backend/test_plan/floorplan.pdf`); all four recovery-snapshot directories ignored. No source directory is broadly ignored; `backend/tests/pdf_fixtures.py` (a `.py` file) is unaffected by the `*.pdf` rule and remains tracked. One observation, not a change: the blanket `*.pdf` rule would also silently ignore a legitimate future *.pdf test fixture anyone tries to commit deliberately — worth a narrower rule if/when that need arises, not now.

---

## CI reproducibility check (Section 15)

Inspected `.github/workflows/ci.yml` for hidden local dependencies: no reference to `_backup_before_flatten`, `_recovery_candidates`, any private/local PDF fixture, or any local-only environment file. Both jobs run from `actions/checkout@v4` (clean clone) using only `backend/requirements.txt`, `frontend/package-lock.json`, and a fresh Postgres service container. Locally simulated with a genuinely fresh (not pre-migrated) Postgres instance and a clean `npm ci` install — see items 8–9 above — rather than trusting the YAML alone.

---

## Deferred technical debt (explicitly not touched in R2.5)

- `requirements-minimal.txt` reconciliation (still diverges from `requirements.txt`; not installed by CI, not cleaned up here).
- `npm audit`'s 7 reported vulnerabilities (1 low, 1 moderate, 5 high) in transitive frontend dependencies — newly observed this session while verifying `npm ci`; not remediated (would be dependency-version churn, out of R2.5's scope).
- Root-level recovery snapshot directories (`_backup_before_flatten/` etc.) — untouched, still gitignored, still on disk.
- 0-byte dead tracked files (`main_simple.py`, `vlm_usage_tracker.py`, `backend/README.md`, `detection_patch.txt`) — untouched.
- `frontend/tsconfig.json` vs. 100%-`.jsx` codebase — untouched, no typed layer decided yet.
- Structured logging, request IDs, error contracts — deferred per Section 11.
- CORS hardening — deferred per Section 12.
- Frontend test suite (Vitest+RTL) — decided, not implemented; R3's job.
- Linting/formatting/static analysis, pre-commit hooks, dependency locking beyond the existing lockfiles, security scanning in CI — all deferred per `PRODUCTION_ROADMAP.md`'s Production-Engineering timing table, unchanged by R2.5.

## Not implemented (per explicit R2.5 scope boundary)

No `LegendEntry`, OCR workflow, `Material` model, `HatchPattern` model, hatch feature extractor, pattern library, tile detector, similarity heatmap, analysis job queue, authentication, microservices, cloud storage, deployment pipeline, or UI redesign were introduced. Confirmed by reviewing every file changed in this release (see the branch's diff against `main`) — all changes are hardening/infrastructure to already-existing R1/R2 surfaces plus one small, explicitly-scoped preview endpoint.
