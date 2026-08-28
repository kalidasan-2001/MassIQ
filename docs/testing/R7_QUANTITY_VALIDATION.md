# R7 — Review & Quantity: Validation

Date: 2026-08-28

All numbers below were captured by actually running the real code in this session — backend `unittest` suites against the real dev Postgres, and the real Chromium browser via Playwright — never estimated.

## 1. Golden geometry vectors (release-critical, R7 sections 12/31)

`backend/tests/test_geometry_service.py`, 11 hand-computed cases against `app.geometry.service.compute_final_area_m2` (page 200×100 points, `real_meters_per_plan_point=1.0`, so 1 point = 1 real meter — chosen purely to keep hand-checked expected values simple):

| Case | Setup | Expected | Result |
|---|---|---|---|
| A. Single accepted region | 20m × 5m | 100 m² | **100 m²** ✅ |
| B. Addition, no overlap | +10m × 5m adjacent | 150 m² | **150 m²** ✅ |
| C. Subtraction inside positive | −4m × 5m fully inside | 80 m² | **80 m²** ✅ |
| D. Overlapping additions | two 100 m² regions overlapping 50 m² | 150 m² (**not** 200, naive sum) | **150 m²** ✅ |
| E. Subtraction extends beyond positive | subtract region 5× larger, only 50 m² actually overlaps | 50 m² (**not** negative) | **50 m²** ✅ |
| Subtraction entirely covers positive | | 0 m² | **0 m²** ✅ |
| Subtraction disjoint from positive | | unchanged (100 m²) | **100 m²** ✅ |
| Overlapping subtractions | two subtracts overlapping each other | union-of-subtracts removed once, not twice | **5000 m²** (of 20000 m² page, verified by hand) ✅ |
| No positive geometry | | 0 m² | **0 m²** ✅ |
| Never negative/NaN/Infinity | 3 adversarial cases | finite, ≥0 | ✅ all 3 |
| Duplicate identical positive rects | 3× the same rect | counted once | **100 m²** ✅ |

All 11 pass. This is the release-critical proof that overlapping accepted detections, overlapping manual additions, and overlapping manual subtractions are never double-counted or double-subtracted.

## 2. Golden compatibility with legacy `quantityEngine.js` (R7 section 7)

`backend/tests/test_quantity_legacy_parity.py`:

- Reproduces `frontend/src/utils/quantityEngine.test.js`'s exact 4 cases as a direct Python reimplementation of the legacy scalar formula — all 4 match exactly (11, 30, 22/55, 0/0).
- For **non-overlapping** geometry (the shape legacy's scalar model implicitly assumes), the new union-based backend calculation is proven to produce the **identical** number as legacy's naive scalar sum, in 4 separate cases (single accepted region, accepted + disjoint addition, accepted − fully-contained subtraction, and the volume formula itself).
- One documented, deliberate divergence: a SUBTRACT rectangle with **zero geometric overlap** against the positive area. Legacy's naive formula would still subtract its full area (a real, silent bug in the legacy path); the correct engine removes nothing. Documented explicitly in the test rather than hidden.

## 3. Review authority (release-critical, R7 section 3)

`backend/tests/test_quantity_service.py`:

| Assertion | Result |
|---|---|
| A `CANDIDATE` region contributes 0 area | ✅ `test_candidate_region_contributes_zero_area` |
| A `REJECTED` region (similarity 0.99) contributes 0 area | ✅ `test_rejected_region_contributes_zero_area` |
| An `ACCEPTED` region (similarity 0.01) contributes its **full** area | ✅ `test_accepted_region_contributes_regardless_of_similarity` — proves similarity never gates/scales participation |
| Mixed candidate/rejected/accepted — only accepted counts | ✅ `test_mixed_statuses_only_accepted_counts` |

## 4. Zero/negative behavior (R7 section 22)

| Case | Result |
|---|---|
| No positive geometry at all | `final_area_m2 = 0.0`, `volume_m3 = 0.0` |
| Subtraction larger than the entire positive region | `final_area_m2 = 0.0` (never negative) |

## 5. Idempotence (R7 section 21)

Verified directly: calculating twice for the same `DetectionRun`/state returns the **same row id** (`test_repeated_calculation_updates_same_row_not_a_duplicate`) and the same numbers across 3 repeated calls (`test_same_state_produces_deterministic_result`). Confirming a result then recalculating resets `status` back to `DRAFT` and clears `confirmed_at` (`test_recalculation_resets_confirmed_status`) — a confirmed number never silently survives a change to the underlying review state.

## 6. Feature-version pre-run guard (R7 section 4)

`backend/tests/test_detection_service.py::test_outdated_feature_version_reference_raises_clear_error`: a `HatchFeatureSet` with a stale `feature_version` now raises `ReferenceFeatureVersionOutdatedError` (`error_code="REFERENCE_FEATURE_VERSION_OUTDATED"`) **before** the run starts, rather than completing with zero candidates.

## 7. Scale model

`backend/tests/test_plan_scale_service.py`: `DECLARED_SCALE` (ratio 100) derives `real_meters_per_plan_point = (0.0254/72) * 100`, verified to 9 decimal places against the hand-computed constant. `CALIBRATED_DISTANCE` (50 points / 5 m) derives exactly `0.1`. Invalid inputs (zero/negative/NaN ratio or distance) rejected with a controlled `InvalidScaleError`. Re-confirming replaces the same row (not a duplicate). Cross-project pages get fully independent scale rows.

## 8. Manual corrections

`backend/tests/test_manual_correction_service.py`: ADD/SUBTRACT creation, listing in creation order, deletion, and **7** invalid-geometry cases rejected (zero width/height, negative width, negative x, extends past the page edge, NaN, Infinity) — all via a controlled `InvalidCorrectionGeometryError`, never a raw stack trace. Ownership/ isolation verified (unknown run, cross-project run access).

## 9. Ownership isolation

Verified at both the service and route layer for all three new concerns (scale, manual corrections, quantity) — a project cannot read or write another project's `PlanScale`/`ManualRegionCorrection`/`QuantityResult`, confirmed via `test_cross_project_*` tests returning the same `DetectionRunNotFoundError`/`PlanScaleNotFoundError`/404 a genuinely-missing resource would.

## 10. Migration up/down/up

`c61d4d05e4c9` (`down_revision = 90498cc645d2`) executed live against the real dev Postgres:

- `upgrade head` → `plan_scales`, `manual_region_corrections`, `quantity_results` created with all columns/FKs/indexes matching the ORM models.
- `downgrade -1` → all three R7 tables and their three native enum types (`plan_scale_method`, `manual_correction_type`, `quantity_result_status`) removed; **R1–R6 tables and enums confirmed intact** via a live `pg_type`/`pg_tables` query.
- `upgrade head` again → full restoration confirmed column-by-column, including the `ck_detection_runs_exactly_one_reference` constraint on the pre-existing `detection_runs` table (proving R7's migration did not disturb R6's own constraint).

## 11. Browser E2E — E2E-07 (mandatory hard gate, R7 section 33)

`frontend/e2e/specs/review-quantity.spec.js`, 3 real-Chromium scenarios, **zero `page.evaluate()` state injection**:

1. **Full workflow**: confirm reference → compute features → run Detection V2 (≥2 real candidates on the real fixture page) → Accept one, Reject another (real clicks) → Manual Add via real mouse drag → Manual Subtract via real mouse drag (both asserted via real `POST .../manual-corrections` responses and visible overlays) → **viewport resize coordinate-resilience check** (see below) → confirm declared scale (1:100) → confirm dimension (0.2 m) → calculate quantity (backend-computed area/volume, `volume == area × dimension` independently re-checked) → **reload** → re-select project/plan/entry → verify accepted/rejected/manual-add/manual-subtract/scale/**identical displayed area and volume** all persist from a fresh server query.
2. **Quantity separation regression** (R7 section 37): run detection, deliberately accept nothing, confirm scale, calculate — `final_area_m2 == 0` and `volume_m3 == 0`, both in the raw API response and the rendered UI.
3. **Invalid-input control** (R7 section 39): the Calculate button is disabled and a clear message is shown before scale is confirmed — no unhandled request, no console error.

All 3 pass. `monitor.assertClean()` (zero unexpected console errors, zero unexpected 5xx) passes on all 3.

## 12. A real bug found and fixed by browser-level resize testing

The mandatory coordinate-resilience check (R7 section 36 — draw a region, resize the viewport, verify the overlay stays over the same physical plan region) **failed on first run**: `usePageSelection.js`'s `viewSize` was captured only once, on the `<img>`'s `onLoad` event, and never updated afterward — so every overlay on the page (pattern/description/detection/manual-correction, not just the R7 additions) silently drifted out of alignment with the plan image after any browser window resize. Fixed with a `ResizeObserver` on the image element that keeps `viewSize` current for the lifetime of the component (`frontend/src/features/legend/usePageSelection.js`). Re-run after the fix: overlay position, expressed as a fraction of the (now differently-sized) image, matches its pre-resize fraction to well within a 1% tolerance. This is the same category of finding R3's own native-image-drag bug was — a real, reproducible defect only a genuine browser-driven test could catch, not a curl-only or component-only check.

## 13. Existing Playwright regression (R7 section 40)

All 10 pre-existing scenarios (smoke, project-plan, legend-workflow, persistence, pattern-library, detection-v2, legacy-workflow, invalid-upload) re-run and remain green after the R7 changes.

## 14. Performance

Quantity calculation (union/subtraction over a handful of rectangles, plus one DB round-trip for regions/corrections/scale) is sub-100ms in every test run observed — no case anywhere near a threshold that would justify async infrastructure, consistent with R6's own "measure, don't guess" performance discipline.

## Conclusion

All mandatory R7 requirements were executed with real, reproducible evidence: release-critical union/subtraction geometry proven correct against 11 hand-computed golden vectors and a DB-backed review-authority matrix; golden parity with the untouched legacy formula established for every non-overlapping case with the one divergence documented honestly; idempotent, versioned, auditable persistence; a real coordinate-tracking bug found and fixed by genuine browser-level testing, not just claimed fixed; and a mandatory, non-state-injected Playwright scenario proving the entire review → manual correction → scale → dimension → quantity → reload workflow end-to-end.
