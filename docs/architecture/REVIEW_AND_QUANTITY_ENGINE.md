# Review & Deterministic Quantity Engine (R7) — Architecture

Date: 2026-08-28
Scope: connects R6's candidate `DetectedRegion`s to an authoritative, backend-computed, persisted `QuantityResult` — human review (accept/reject + manual add/subtract), a persisted drawing scale, an explicitly confirmed dimension, and a correct union/subtraction geometry engine, none of which existed before this release.

## Product rule: human review is authoritative, math is deterministic

```
CV suggests (R6 candidates)
  -> user accepts/rejects
  -> user manually adds missed geometry / subtracts wrong geometry
  -> validated geometry
  -> confirmed scale
  -> deterministic area (union/subtraction, not scalar summation)
  -> confirmed height/thickness
  -> deterministic volume
  -> persisted, auditable QuantityResult
```

Nothing here ever changes a `DetectedRegion.status` automatically, and nothing computes a quantity without an explicit `POST .../quantity` call carrying an explicitly confirmed dimension. Similarity score never influences participation (R7 section 3) — `CANDIDATE` and `REJECTED` regions always contribute exactly zero area, `ACCEPTED` regions always contribute fully regardless of how low their similarity was.

## Audit of the pre-existing (legacy) quantity implementation

Before any code changed, `frontend/src/utils/quantityEngine.js` and its only caller (`frontend/src/components/PlanViewer.jsx`, the original filesystem-only MVP flow — entirely separate from the Project/Plan/LegendEntry/DetectionRun stack R3-R6 built) were read in full, not rewritten from memory:

- **Formula**: `final_area_m2 = accepted + added - subtracted`; `volume_m3 = final_area_m2 * confirmed_height_m`. A pure function, four scalar number inputs, no geometry awareness at all.
- **Inputs**: `PlanViewer.jsx` computes each scalar by **naively summing** `region.w * region.h` (or `area_m2 * count` for line-item subtractions like windows/doors) across every accepted detection / add-correction / subtract-correction independently, then divides by `scale.pixelsPerMeter ** 2`. **There is no union/overlap handling anywhere in the legacy path** — two overlapping accepted detections, or an add-correction drawn on top of an accepted detection, are silently double-counted today. This is the exact gap R7 was asked to close for the new pipeline.
- **Units**: pixels internally, divided by `pixelsPerMeter²` for area; height is a raw meters text input.
- **Rounding**: `buildQuantityResult` itself never rounds — `PlanViewer.jsx`'s own `round()` helper only formats at display time (4 decimal places for the quantity table). R7 follows the exact same "round only at the presentation boundary" discipline.
- **Scale**: `scale.pixelsPerMeter` lives **only** in `PlanViewer.jsx`'s own React `useState` — confirmed by the user via two plain number inputs, never sent to the backend, never persisted. Same for the confirmed height (`heightMeters` state, freeform text). **This is the gap R7 section 13 required closing**: no PlanScale-equivalent existed anywhere in the DB before this release.
- **Tests**: `quantityEngine.test.js`'s 5 existing cases were left completely unmodified and are the literal golden vectors reproduced in `backend/tests/test_quantity_legacy_parity.py` (see "Golden compatibility" below).

`PlanViewer.jsx`/`quantityEngine.js`/`RegionEditor.jsx` are **not touched by R7** — the legacy MVP flow keeps working exactly as before. R7 only adds a new, parallel, backend-authoritative path onto the R3-R6 Project/Plan/LegendEntry/DetectionRun stack.

## Quantity authority: one implementation, backend-owned

`QuantityService` (`backend/app/services/quantity_service.py`) is the single, authoritative, persisted calculator. It never trusts a frontend-provided `final_area` — the only inputs a caller supplies are the `DetectionRun` to calculate for and an explicitly confirmed dimension; every other input (accepted `DetectedRegion`s, `ManualRegionCorrection` ADD/SUBTRACT rows, the page's confirmed `PlanScale`) is derived from persistence. The frontend never independently recomputes a "real" quantity — `QuantityPanel.jsx` only ever displays what the backend returned.

## Golden compatibility with the legacy formula

`backend/tests/test_quantity_legacy_parity.py` reproduces `quantityEngine.test.js`'s exact 4 cases as a direct Python reimplementation of the legacy scalar formula, then proves the new union-based `app.geometry.service.compute_final_area_m2` produces the **identical** number for every case where the input geometry has **zero overlap** — exactly the shape legacy's scalar model implicitly assumes. The one documented, deliberate divergence: a SUBTRACT rectangle placed with **no geometric overlap at all** against the positive area. Legacy's naive scalar formula would still subtract its area (a real, silent bug); the correct union/subtraction engine removes nothing, because nothing is actually there to remove. This is called out explicitly in the test, not glossed over.

## Geometry model — provenance stays separate from math

- **`ManualRegionCorrection`** (`backend/app/models/manual_region_correction.py`): one human-drawn ADD or SUBTRACT rectangle, scoped to exactly one `DetectionRun` (not just one `PlanPage`) — a second detection run on the same page starts a fresh review session with its own corrections, mirroring how R6 already treats a new run as a fresh set of `DetectedRegion`s. Deliberately its own table, never a fake `DetectedRegion` with a special status — a manual correction has no similarity/evidence_coverage/tile_count, it was never a CV result.
- Same normalized `[0,1]` page-fraction coordinate contract every other overlay in this app already uses (R3's `pattern_x/y/width/height`, R6's `DetectedRegion`) — no second coordinate convention was created. `frontend/src/features/legend/coordinates.js`'s existing `draftToNormalizedRect`/`normalizedToDisplayRect` are reused unmodified for manual Add/Subtract drawing and overlay rendering; `usePageSelection.js` needed **zero code changes** — it was already mode-agnostic (`mode` is just a string), so `'manual_add'`/`'manual_subtract'` work identically to `'pattern'`/`'description'`.
- Geometry validation (`ManualCorrectionService`'s `_validate_normalized_rect`): rejects negative/zero width or height, NaN/Infinity, and any rect extending outside `[0,1]` — a controlled `InvalidCorrectionGeometryError` (→ HTTP 400), never a raw geometry-library stack trace.

## Union/subtraction geometry — release-critical

`app/geometry/service.py`'s `compute_final_area_m2`:

```
PositiveGeometry = union(accepted DetectedRegions, manual ADD corrections)
NegativeGeometry = union(manual SUBTRACT corrections)
FinalGeometry     = PositiveGeometry - NegativeGeometry
FinalArea         = area(FinalGeometry)   -- clamped >= 0, never NaN/Infinity
```

**Geometry library decision (R7 section 12)**: Shapely was already present in this project's fully-resolved dependency tree — a transitive dependency of `rapidocr-onnxruntime` (added in R3), confirmed via `pip show shapely`. Rather than hand-roll rectangle-union/subtraction math (explicitly discouraged by the release spec) or introduce a brand-new dependency, R7 pins the already-resolved `shapely==2.1.2` explicitly in `requirements.txt` — a documented, intentional dependency with **no new supply-chain surface**, since every environment that already installs `requirements.txt` (including CI) already resolves this package today.

All boolean operations happen in real physical **meters**, not raw normalized fractions multiplied by one scalar — a page is not generally square, so x and y each need their own page-dimension scale factor applied *before* any union/difference; only then is Shapely's own `.area` already a correctly-scaled square-meter number.

Verified directly (`backend/tests/test_geometry_service.py`, 11 hand-computed cases + `backend/tests/test_quantity_service.py`'s DB-backed equivalents): overlapping accepted regions counted once, overlapping ADD corrections counted once, overlapping SUBTRACT corrections not double-subtracted, a SUBTRACT extending beyond the positive region removes only the intersecting part (never negative), a SUBTRACT entirely covering the positive region yields exactly `0.0`, zero positive geometry yields `0.0`.

## Scale model — closing a real, confirmed gap

`PlanScale` (`backend/app/models/plan_scale.py`), one row per `PlanPage` (unique constraint), confirmed explicitly by a human — never derived automatically from OCR/AI. Two supported methods, both resolving to a single authoritative derived number, `real_meters_per_plan_point`, which is the *only* field `QuantityService` ever reads:

- **`DECLARED_SCALE`** (e.g. "1:100"): assumes the `PlanPage`'s own persisted PDF-point geometry represents genuine 100%-print physical size (1 PDF point = 1/72 inch of real printed paper) — a standard, defensible architectural-drawing convention, documented here as an assumption, not asserted as universal fact. `real_meters_per_plan_point = (0.0254/72) * declared_ratio`.
- **`CALIBRATED_DISTANCE`**: the user selects two points on the page and enters the true real-world distance between them. `real_meters_per_plan_point = calibrated_distance_real_m / calibrated_distance_plan_points`.

Re-confirming replaces the existing row in place (matches `HatchFeatureSet`'s own "recompute replaces" precedent) — a page has exactly one current scale. Both raw method-specific inputs are kept alongside the derived number purely for reproducibility/auditability, even though only the derived number is ever read by the calculator.

## Units

Canonical backend units throughout: normalized `[0,1]` page-fraction coordinates, m² area, m height/thickness, m³ volume. The frontend's `QuantityPanel.jsx` accepts mm for the LegendEntry thickness *suggestion* only (`thickness_mm / 1000`, one conversion, in one place) — the value actually sent to `POST .../quantity` is always already in meters, matching R7 section 16's "do not scatter unit conversions across components."

## Feature-version pre-run guard (R7 section 4)

The R6 independent review flagged a LOW future-risk: an outdated reference `HatchFeatureSet` would still be accepted by `DetectionService.start_run`, every tile would then fail `combined_similarity`'s own version-mismatch gate, and the run would complete as `COMPLETED` with zero candidates — indistinguishable from "genuinely nothing found." `DetectionService._require_current_feature_version` now checks `feature_set.feature_version == app.hatch.config.FEATURE_VERSION` before a run starts, raising `ReferenceFeatureVersionOutdatedError` (`error_code = "REFERENCE_FEATURE_VERSION_OUTDATED"`) — a plain equality check against the one current constant, not a version-compatibility matrix or migration framework, and the detector algorithm itself is unchanged.

## QuantityResult — authoritative, not duplicative

`QuantityResult` (`backend/app/models/quantity_result.py`), unique on `detection_run_id` — recalculating **updates the same row in place** (idempotence, R7 section 21) rather than accumulating duplicates. Every recalculation resets `status` back to `DRAFT` and clears `confirmed_at`: a `CONFIRMED` result reflects a specific, already-seen number, and if the underlying review state changes and the number is recomputed, that confirmation no longer silently applies to the new number. Deliberately does **not** duplicate region/correction geometry — `DetectedRegion`/`ManualRegionCorrection` remain the provenance; the result row stores only the computed numbers plus cheap summary counts (`accepted_region_count`/`manual_add_count`/`manual_subtract_count`) for auditability without re-querying three tables.

`app.geometry.config.CALCULATION_VERSION = "1.0"` is recorded on every row, independent of R6's `DETECTOR_VERSION` — a future change to the union/subtraction or rounding semantics is never silently compared against an older result as if equivalent.

## Auditability

A `QuantityResult` traces back, without ambiguity, to: `project_id`/`plan_id`/`plan_page_id` → `detection_run_id` → the run's own `reference_legend_entry_id`/`reference_pattern_library_entry_id` → the accepted `DetectedRegion`s and `ManualRegionCorrection`s that actually fed the calculation (queryable, though not duplicated onto the result row) → the `PlanScale` in force at calculation time → the `confirmed_dimension_m` explicitly supplied → `calculation_version`. Every persisted `QuantityResult` is fully explainable after the fact.

## API surface

```
PATCH  /.../detection-runs/{run_id}/regions/{region_id}                  (R6, unchanged -- accept/reject)
POST   /.../detection-runs/{run_id}/manual-corrections
GET    /.../detection-runs/{run_id}/manual-corrections
DELETE /.../detection-runs/{run_id}/manual-corrections/{correction_id}
GET    /.../pages/{page_number}/scale
PUT    /.../pages/{page_number}/scale
POST   /.../detection-runs/{run_id}/quantity        (calculate -- idempotent update-in-place)
GET    /.../detection-runs/{run_id}/quantity
POST   /.../detection-runs/{run_id}/quantity/confirm
```

Thin routes throughout — every one maps a domain exception to a controlled 400/404/422, no raw stack traces, matching R1-R6's established `_not_found`/exception-mapping pattern exactly.

## Frontend (functional, not redesigned)

`ManualCorrectionPanel.jsx` (Add/Subtract mode toggle + list, explicit "Added"/"Subtracted" text labels, not just color — R7 section 26) and `QuantityPanel.jsx` (scale confirmation, confirmed dimension, calculate, area/volume/DRAFT-vs-CONFIRMED display, review counters) both render in `LegendWorkspace.jsx` once a completed `DetectionRun` exists, reusing the exact same `usePageSelection`/`coordinates.js` mechanism R3/R6 already validated — zero new coordinate math, zero new drag-handling code path. Overlay CSS reuses the legacy MVP's own `.overlay-add`/`.overlay-subtract` classes (already defined in `styles.css`, same visual language).

## Known limitations

- `DECLARED_SCALE`'s 100%-print-scale assumption is a standard architectural convention, not a universal guarantee — a plan exported at a non-100% print scale needs `CALIBRATED_DISTANCE` instead; this is a UX/documentation matter, not a math defect.
- The legacy MVP flow (`PlanViewer.jsx`) and the new R3-R7 stack remain two separate, non-unified quantity experiences, exactly as R6 left the two review experiences — a future release should decide whether to consolidate them.
- Export (`ExportButton.jsx`/`/export-excel`) does not yet read from `QuantityResult` — out of scope for R7 per its own explicit "do not implement R8 export redesign" boundary.
