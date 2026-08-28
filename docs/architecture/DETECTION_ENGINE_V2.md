# Detection Engine V2 (R6) — Architecture

Date: 2026-08-28
Scope: locates CANDIDATE hatch regions across an entire `PlanPage`, starting from a reference pattern (a confirmed `LegendEntry` or a project's `PatternLibraryEntry`), by reusing R4's feature extractor and R5's similarity scorer — no new CV algorithm, no ML model, no embeddings. R6 produces candidates only; a human reviews, accepts, or rejects every one, and only that accepted state ever reaches the deterministic quantity engine.

## Product rule: detection is advisory, never authoritative

```
CV suggests -> user reviews -> user accepts/rejects/corrects -> deterministic quantity engine calculates
```

Nothing in `DetectionRun`/`DetectedRegion` or `DetectionService` ever writes to a quantity/area/volume field — there is no such field on either model, and `app/services/detection_service.py`'s own module docstring states this boundary explicitly as the reason the module exists in its current shape. `DetectedRegion.status` starts `CANDIDATE` and only changes via an explicit `PATCH` a human triggers.

## Reference provenance (no arbitrary image paths)

A run originates from exactly one of:
- a confirmed `LegendEntry` with a current `HatchFeatureSet` (same explicit-computation-only gate R4/R5 already enforce — `ReferenceFeatureSetRequiredError` if none exists yet), or
- a project's own `PatternLibraryEntry` (which itself already traces back through the same chain, per R5).

Enforced twice: a Pydantic `model_validator` on `StartDetectionRunRequest` (exactly one of `legend_entry_id`/`pattern_library_entry_id`), and again in `DetectionService._resolve_reference` (defense in depth, same pattern R3's `RegionSelection` and R5's `add_entry` already use). No client-supplied filesystem path is ever accepted anywhere in this flow — the page image is always resolved through `PlanService.get_page` + `StorageService.resolve_preview`, exactly as R3/R4 already do for crops.

## Domain model

`DetectionRun` (`backend/app/models/detection_run.py`): `project_id`/`plan_id`/`plan_page_id`, exactly one of `reference_legend_entry_id`/`reference_pattern_library_entry_id` (DB `CHECK` constraint, not just application code), `feature_version` + `detector_version` (see versioning below), `status` (`PENDING`/`RUNNING`/`COMPLETED`/`FAILED`), `parameters` (JSON — the exact `tile_size_px`/`stride_px`/`candidate_threshold`/`min_evidence_coverage` this run used), tile/region counts, a safe `error_message`, `created_at`/`completed_at`.

`DetectedRegion` (`backend/app/models/detected_region.py`): a plain rectangle (`x`/`y`/`width`/`height`, the same normalized page-fraction coordinate contract every other overlay in this app uses), `similarity`/`evidence_coverage` (region-level, see scoring below), `tile_count`, and `status` (`CANDIDATE`/`ACCEPTED`/`REJECTED`). Deliberately a bounding box, not a polygon — `RegionEditor.jsx`/`quantityEngine.js` already work with rectangles, and R6 section 14 explicitly asks not to overbuild polygon segmentation the existing pipeline doesn't need.

## Detector versioning

`app.detection.config.DETECTOR_VERSION` ("1.0") is bumped whenever tile size, stride, gating, thresholding, or merging *semantics* change — independent of R4's `FEATURE_VERSION` and R5's similarity engine, both reused unmodified. Every `DetectionRun` records both versions plus its exact `parameters`, so a result is always reproducible and never silently compared against a differently-configured run as if equivalent.

## Package layout (`backend/app/detection/`)

Mirrors R4/R5's own package discipline — one small, pure, independently-testable module per concern, no FastAPI/SQLAlchemy/filesystem coupling anywhere except in `DetectionService` (the only thing that resolves a page image and persists results):

```
config.py    -- every named threshold/parameter, documented, calibrated
models.py    -- Tile / TileEvaluation / CandidateRegion / DetectionResult dataclasses
tiler.py     -- deterministic page -> tile grid
gating.py    -- tile quality gate (reuses R4's own angle-evidence signal)
merging.py   -- connected-components grouping of candidate tiles
scoring.py   -- region bounding box + median/mean score aggregation
detector.py  -- run_detection(page_image, reference) -> DetectionResult (the orchestrator)
```

## Tile strategy

**Tile size (128px), measured, not guessed.** Extracting R4's own benchmark hatch families (10px/20px/30px spacing) at candidate tile sizes showed 64px tiles fail to reliably recover angle/spacing evidence for wide-spacing families (family F's 30px-spacing cross-hatch reported zero dominant angles at 64px); 96px and above recovered reliable evidence for every tested spacing:

| Tile size | Family A (10px) | Family C (20px) | Family F (30px, sparse cross) |
|---|---|---|---|
| 64px | 1 angle, spacing available | 1 angle, spacing available | **0 angles, no spacing** |
| 96px | 1 angle, spacing available | 1 angle, spacing available | 2 angles, spacing available |
| 128px | 1 angle, spacing available | 1 angle, spacing available | 2 angles, spacing available |

128px was chosen over 96/192/256 as the smallest size with a comfortable margin above the 96px minimum — smaller tiles give finer region-boundary resolution and more tiles per page for the same coverage.

**Stride (96px, 25% overlap), also measured.** Hatch regions will not align to the tile grid, so some overlap is a safety margin against a real region landing split across a boundary and under-evidenced on both sides. Measured tile-count cost on a realistic 1800×1200 page: non-overlapping tiling produces 150 tiles, 25% overlap 247 (1.65×), 50% overlap 504 (3.36×). On the synthetic benchmark, recall was identical (9/9 ground-truth targets found) at all three overlap levels — reported honestly rather than claiming a recall benefit that wasn't actually measured. 25% overlap was kept as a reasoned safety margin for real pages at a modest 1.65× cost, not because it improved this particular benchmark's own recall.

## Tile preprocessing / feature extraction reuse

Every tile is extracted with the exact same `HatchFeatureExtractor` class R4 already validated — `detector.py` never re-implements or forks the CV pipeline. Because the reference and every tile are extracted with the same code at the same run time, `feature_version` consistency is automatic, not incidental. `combined_similarity.compare`'s own feature-version gate is still consulted for defense in depth (a mismatch would be structurally surprising, not expected).

## Tile quality gating

A tile is skipped (never compared against the reference, never persisted as a candidate) if `HatchFeatureExtractor` found no reliable angle evidence at all (`dominant_angles` is empty) — the exact same signal R4's own `MIN_ANGLE_EVIDENCE_PX` gate already produces, not a second, independently-tuned threshold that could disagree with it. Skipped tiles are counted (`DetectionRun.tiles_skipped`), never silently dropped from the record.

## Similarity reuse — one source of truth

`detector.py` calls `app.hatch.similarity.combined_similarity.compare()` directly — the identical function R5's Project Pattern Library uses for LegendEntry-to-LegendEntry comparison. No second production similarity formula exists anywhere in this codebase. A tile's `ComparableFeatures` is built the same way R5 already builds them (`ComparableFeatures.from_features`).

## Similarity map

For every tile that clears the quality gate, a `TileEvaluation` records its location (row/col, pixel and normalized rect), `similarity`, `evidence_coverage`, and whether it became a candidate — the logical heatmap R6 section 11 requires. This is an in-memory structure for the duration of one run (not a per-tile DB table — persisting hundreds of raw tile rows per run was judged unnecessary bloat; only the final merged `DetectedRegion`s are persisted, matching R6 section 4's "keep the model small"). `DetectionRun.tile_count`/`tiles_evaluated`/`tiles_skipped` are the persisted summary of this map.

## Candidate thresholding — not a blind 0.8

`CANDIDATE_SIMILARITY_THRESHOLD = 0.65`, calibrated against the R6 synthetic detection benchmark, not assumed: target hatch regions scored 0.75–0.98 against their own reference on the synthetic fixtures; kept deliberately more permissive than R5's own `HIGH_SIMILARITY_THRESHOLD` (0.75), per R6 section 21's explicit recall-over-precision priority for this first release. `MIN_EVIDENCE_COVERAGE_FOR_CANDIDATE = 0.5` mirrors R5's own `evidence_coverage` protection — a tile-vs-reference comparison built from too little available evidence cannot count as a candidate regardless of its raw similarity. Raw similarity, evidence coverage, and the candidate decision are three distinct, separately-inspectable values at every stage — never conflated into one number.

## Neighbor merging

`cv2.connectedComponents` (8-connectivity) over a boolean tile-grid mask — the simplest defensible method: tiles already sit on a regular grid, so this is exactly the well-tested, already-a-dependency primitive R4/the legacy detector's own OpenCV usage already relies on, rather than a hand-rolled graph or flood-fill. 8-connectivity (not 4) was chosen because a real hatch region's candidate tiles frequently touch only at a corner where the grid happens to cross the region's own diagonal edge — 4-connectivity was found (via the synthetic benchmark) to needlessly split one visually contiguous region into two.

## Region geometry and scoring

A `CandidateRegion`'s box is the union bounding box of its member tiles' normalized rects — a rectangle, not a polygon (see Domain model above for why). Its score is the **median** tile similarity (not max, not mean) — a single strong tile at a region's edge must not make a mostly-weak region look confidently scored, and a mean is more sensitive than the median to a handful of low-evidence-but-still-candidate tiles the merge step may include near a boundary. Evidence coverage is aggregated as a plain **mean** — it doesn't carry the same single-outlier risk similarity does.

## Legacy detector coexistence

The legacy multi-scale `matchTemplate` detector (`backend/app/services/hatch_detection.py`) is completely untouched by R6 — not deleted, not rewritten, not automatically combined with V2. `backend/tests/test_detection_legacy_comparison.py` runs both independently on the same synthetic fixtures and reports both sets of metrics without ever merging their outputs; see the benchmark doc for the measured, honestly-reported comparison (including where legacy still performs comparably).

## Persistence and human review

`DetectionService.start_run` is synchronous end-to-end for this first release (R6 section 26 — measured runtimes stay well within a normal request, see the benchmark doc's performance section) but still records explicit `PENDING`→`RUNNING`→`COMPLETED`/`FAILED` states, never leaving a run ambiguously "in progress" forever. No partial `COMPLETED` state: region persistence and the `COMPLETED` status update happen in one transaction; any failure before that point rolls back everything and records `FAILED` in a fresh, minimal transaction of its own — verified directly (`test_detection_service.py::test_corrupt_preview_fails_the_run_cleanly_not_a_crash`). `error_message` is always a safe, human-readable string — the actual exception (if any) is logged server-side only, never returned to the API caller.

`update_region_status` is the only way a `DetectedRegion`'s status ever changes. The frontend restores the most recent run for a page (and its regions' review state) purely by querying the database again (`GET .../pages/{page_number}/detection-runs`) — no client-side caching of run identity, so a browser reload shows exactly what's actually persisted, proven end-to-end by the R6 Playwright scenario.

## Frontend (minimal, functional)

`DetectionPanel.jsx` (list + accept/reject actions, mirrors R5's `PatternMatchesPanel.jsx`) and region overlays on the existing shared plan-page image in `LegendWorkspace.jsx` (three new CSS states: candidate/accepted/rejected, same border+fill visual language as every prior overlay in this app). No new correction/quantity model was built — `DetectedRegion` is deliberately separate from, and does not feed, the existing `quantityEngine.js`/`RegionEditor.jsx` pipeline in this release (see Known limitations).

## Known limitations

- Accepted `DetectedRegion`s are not yet wired into the existing quantity-export pipeline (`quantityEngine.js`/`ExportButton.jsx`) — R6's release gate only requires that quantity is never *automatically* modified, which holds structurally (no such field exists on either R6 model); actually consuming an accepted region's area is deferred to a future release.
- The candidate threshold (0.65) and evidence-coverage floor (0.5) are calibrated against the R6 synthetic benchmark plus one real fixture page — not a large, varied real-plan corpus. See the benchmark doc's real-plan section for the honest, measured false-positive behavior this surfaced (title-block text and a description box border both occasionally produced candidate-scoring tiles).
- `MAX_TILES_PER_RUN` (4000) is a safety cap, not a scaling solution — an extremely large or oddly-shaped page could still legitimately hit it; `TooManyTilesError` is raised cleanly rather than left to degrade silently.
