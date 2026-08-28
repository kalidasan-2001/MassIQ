# R7 — Review & Deterministic Quantity Integration: Checklist

Date: 2026-08-28
Repository: `C:\Users\kalid\MassIQ`, branch `feature/r7-review-quantity-integration` (created from `main` after fast-forward-merging `feature/r6-detection-engine-v2`, per R6's independent review approval)
Scope: connects R6's candidate `DetectedRegion`s to an authoritative, backend-computed, persisted `QuantityResult` via human review (accept/reject + manual add/subtract), a persisted drawing scale, and a correct union/subtraction geometry engine.

Status legend: **PASS** (executed with evidence), **FAIL**, **BLOCKED**, **DEFERRED**. PASS requires executed evidence, not code inspection alone.

---

## Branch and baseline

**PASS.** R6 (`feature/r6-detection-engine-v2`) was confirmed independently reviewed and approved, but not yet merged into `main`. Fast-forward merged (`git merge --ff-only`, zero-conflict). Baseline re-verified on `main` after the merge: `alembic current`/`heads` → `90498cc645d2 (head)`; backend suite → 469 tests, 0 failures; `npx vitest run` → 25 passed; `npm run build` → 98 modules; `npx playwright test --project=chromium` → 10 passed. `feature/r7-review-quantity-integration` created from `main` only after this full green baseline.

## Legacy quantity audit (R7 section 5)

**PASS.** `frontend/src/utils/quantityEngine.js` and its only caller (`PlanViewer.jsx`, the separate legacy MVP flow) read in full before any code changed. Documented: naive scalar area summation with **no overlap handling at all** (a real, pre-existing gap); scale/height live only in ephemeral React state, never persisted; rounding happens only at display time. See `docs/architecture/REVIEW_AND_QUANTITY_ENGINE.md`'s audit section for the complete writeup. Legacy code itself was **not modified**.

## Human authority (release-critical, R7 section 3)

**PASS.** Verified directly at the service layer: `CANDIDATE` and `REJECTED` regions always contribute `0.0` area regardless of similarity; an `ACCEPTED` region with similarity as low as `0.01` contributes its **full** area — similarity never gates or scales participation. `update_region_status` (R6, unchanged) remains the only path that ever changes a `DetectedRegion.status`; nothing in R7 auto-accepts.

## Feature-version pre-run guard (R7 section 4)

**PASS.** `DetectionService._require_current_feature_version` raises `ReferenceFeatureVersionOutdatedError` (`error_code="REFERENCE_FEATURE_VERSION_OUTDATED"`) before a run starts if the reference's `feature_version` doesn't match the current `FEATURE_VERSION` constant — verified directly (`test_outdated_feature_version_reference_raises_clear_error`). The detector algorithm itself is unchanged; this is a plain equality pre-check, not a version-compatibility framework.

## Geometry model / provenance

**PASS.** `ManualRegionCorrection` is its own table (not a fake `DetectedRegion`), scoped to one `DetectionRun`, same normalized `[0,1]` coordinate contract as every other overlay. `_validate_normalized_rect` rejects negative/zero width-height, NaN/Infinity, and out-of-page-bounds rects with a controlled `InvalidCorrectionGeometryError` — verified against 7 distinct invalid inputs.

## Coordinate contract (R7 sections 9-10)

**PASS.** No second coordinate convention was created — `coordinates.js`'s existing `draftToNormalizedRect`/`normalizedToDisplayRect` are reused unmodified for manual Add/Subtract; `usePageSelection.js` required zero changes to support the two new modes (it was already mode-agnostic). One real bug found and fixed via genuine browser resize testing: `viewSize` was captured only once on image load and never updated on window resize, so every overlay on the page silently drifted after a resize. Fixed with a `ResizeObserver`; re-verified via Playwright (overlay position, as a fraction of the image, stable to well within 1% after a resize).

## Union/subtraction geometry (release-critical, R7 section 12)

**PASS.** Shapely (`shapely==2.1.2`) — already present in the fully-resolved dependency tree via `rapidocr-onnxruntime`, now pinned explicitly, no new supply-chain surface. `app.geometry.service.compute_final_area_m2` verified against 11 hand-computed golden cases (`test_geometry_service.py`) plus the DB-backed review-authority matrix (`test_quantity_service.py`): overlapping positives counted once, overlapping subtracts not double-subtracted, subtraction extending beyond the positive region removes only the intersection, subtraction fully covering the positive region yields exactly `0.0`, zero positive geometry yields `0.0`, never negative/NaN/Infinity.

## Golden compatibility with legacy (R7 section 7)

**PASS.** `test_quantity_legacy_parity.py` reproduces `quantityEngine.test.js`'s own 4 cases exactly, then proves the new union-based calculation equals legacy's naive scalar sum for every non-overlapping case — the one documented divergence (a fully-disjoint subtraction) is legacy's own silent bug, not a new-code regression.

## Scale model (R7 sections 13-15)

**PASS.** `PlanScale`, one row per `PlanPage`, confirmed only via an explicit user action (`DECLARED_SCALE` or `CALIBRATED_DISTANCE`), never from OCR/AI automatically. Both resolve to one authoritative `real_meters_per_plan_point`; raw method inputs kept for reproducibility. Verified to 9 decimal places against hand-computed constants for both methods. Persists across a fresh session/reload.

## Units (R7 section 16)

**PASS.** Canonical backend units (normalized coordinates, m², m, m³) throughout; the one mm→m conversion (LegendEntry's `thickness_mm` suggestion) happens in exactly one place (`QuantityPanel.jsx`), never scattered.

## Quantity authority (R7 section 6)

**PASS.** `QuantityService` is the single, backend-authoritative calculator; it never trusts a frontend-provided `final_area` — every geometry/scale input is derived from persistence. The frontend only ever displays what the backend returned.

## QuantityResult model / versioning / idempotence (R7 sections 18-21)

**PASS.** Unique on `detection_run_id` — recalculation updates the same row (verified: identical row id across repeated calls, identical numbers across 3 repeated calls with unchanged state). `calculation_version` (`"1.0"`) recorded on every row. Confirming then recalculating resets `status` back to `DRAFT` and clears `confirmed_at` — verified directly.

## Zero/negative behavior (R7 section 22)

**PASS.** No positive geometry → `0.0`/`0.0`. Subtraction larger than the positive region → `0.0`, never negative. No NaN/Infinity possible (defensive clamp in `compute_final_area_m2`, plus dimension validation rejecting NaN/Infinity/≤0 at `QuantityService.calculate`'s own boundary).

## Precision/rounding (R7 section 23)

**PASS.** Full precision kept through every intermediate geometry/DB operation; rounding happens only at the `QuantityPanel.jsx` display boundary (2/3/3 decimals for area/dimension/volume respectively), same discipline the legacy `PlanViewer.jsx` already used.

## API

**PASS.** Thin routes: manual-corrections (POST/GET/DELETE), plan-scale (GET/PUT), quantity (POST calculate / GET / POST confirm) — all mapping domain exceptions to controlled 400/404/422 responses, verified via 13 dedicated route-level tests plus the existing detection-runs routes' accept/reject (unchanged).

## Review UI / state visibility / counters (R7 sections 25-27)

**PASS.** `ManualCorrectionPanel.jsx`/`QuantityPanel.jsx` show explicit "Added"/"Subtracted"/"Confirmed"/"Draft" text labels, not color alone. Review counters (candidates/accepted/rejected/manual additions/manual subtractions) displayed; no fabricated aggregate confidence score anywhere.

## Persistence across reload (R7 section 29)

**PASS.** Proven both at the service layer (fresh-session tests for scale/corrections/quantity) and end-to-end through the real browser: E2E-07 reloads the page and confirms accepted/rejected/manual-add/manual-subtract/scale/**identical displayed area and volume** all persist, sourced from fresh server queries.

## Backend tests

**PASS.** **538 tests, 0 failures** (469 R6 baseline + 69 new: 11 geometry + 9 legacy-parity + 8 plan-scale + 9 manual-correction + 18 quantity-service + 13 routes + 1 feature-version guard), executed against the real dev Postgres.

## Frontend unit tests

**PASS.** `npx vitest run` → **44 tests, 0 failures** (25 baseline + 8 `ManualCorrectionPanel.test.jsx` + 11 `QuantityPanel.test.jsx`).

## Frontend build

**PASS.** `npm run build` → **100 modules**, 0 errors (98 baseline + 2 new components).

## Playwright — mandatory hard gate (R7 sections 33-40)

**PASS.** `npx playwright test --project=chromium` → all scenarios green, including the new `E2E-07` (3 scenarios: full workflow, quantity-separation regression, invalid-input control) driven entirely through real Chromium pointer/mouse input, zero `page.evaluate()` state injection. A genuine coordinate-tracking bug (stale `viewSize` after browser resize) was found by the mandatory resize check and fixed in `usePageSelection.js` — not just claimed fixed, re-verified passing after the fix. All pre-existing scenarios (smoke, project-plan, legend-workflow, persistence, pattern-library, detection-v2, legacy-workflow, invalid-upload) remain green.

## Migration up/down/up

**PASS.** `c61d4d05e4c9` executed against the real dev Postgres: upgrade creates all three tables/enums; downgrade removes exactly those three tables/enums while R1–R6 tables/enums (including R6's `ck_detection_runs_exactly_one_reference` constraint) remain intact, verified via a live `pg_type`/`pg_tables` query; upgrade again fully restores everything.

## Performance

**PASS.** Quantity calculation (a handful of rectangle union/difference operations plus one DB round-trip) measured sub-100ms in every observed run — no case near a threshold that would justify async infrastructure.

## CI compatibility

**PASS (by construction).** One new pinned dependency (`shapely==2.1.2`), already fully resolved transitively before this release — no new supply-chain surface, no GPU, no external API, no customer/private plan data.

## Scope compliance

**PASS.** No R8 export redesign, no PDF report generation, no ML/embeddings/vector DB, no new Pattern Library hierarchy, no automatic material truth, no automatic acceptance, no Celery/Kafka/Redis, no microservice split. Reviewed every file changed in this release.

---

## Deferred technical debt

- `ExportButton.jsx`/`/export-excel` does not yet read from `QuantityResult` — explicitly out of scope for R7 (its own "do not implement R8 export redesign" boundary).
- The legacy MVP flow (`PlanViewer.jsx`) and the new R3-R7 stack remain two separate, non-unified quantity experiences — unchanged from the situation R6 already left; a future release should decide whether to consolidate them.
- `DECLARED_SCALE`'s 100%-print-scale assumption is a standard but non-universal architectural convention — documented, not silently assumed correct for every possible plan.

## Risks before R8

- Now that quantity is authoritative and persisted, a future release wiring `QuantityResult` into export should double-check `calculation_version` handling if the union/subtraction formula is ever revised.
- The manual-correction review UI has no bulk/undo-multiple operation yet — fine for the volumes exercised so far, but worth revisiting if real usage produces many corrections per run.
- The `usePageSelection.js` resize fix uses `ResizeObserver`, which is supported by all evergreen browsers this app targets but was not explicitly feature-detected beyond a `typeof` guard — acceptable for now, worth a note if a legacy-browser requirement is ever introduced.

---

**No R8 work (export redesign, PDF reports, ML segmentation, embeddings, automatic acceptance, global library, async infrastructure, microservice split) was introduced.** STOP here.
