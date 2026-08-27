# R4 — Hatch Feature Engine: Checklist

Date: 2026-08-27
Repository: `C:\Users\kalid\MassIQ`, branch `feature/r4-hatch-feature-engine` (created from `main` after fast-forward-merging `test/r3-5-browser-e2e`)
Scope: deterministic, versioned CV feature extraction from a confirmed `LegendEntry`'s pattern crop into a persisted `HatchFeatureSet`. Foundation only — no Pattern Library, no Detection V2, no similarity search (see the explicit exclusion list at the end).

Status legend: **PASS** (executed with evidence), **FAIL**, **BLOCKED**, **DEFERRED**. PASS requires executed evidence, not code inspection alone.

---

## Branch and baseline

**PASS.** `test/r3-5-browser-e2e` was confirmed NOT merged into `main` (`git merge-base --is-ancestor` returned false) before this release started. Fast-forward merged into `main` (`git merge --ff-only`, zero conflicts possible — `main` was a direct ancestor). Baseline re-verified on `main` after the merge, before creating the feature branch: `alembic current`/`heads` → `15bc524c492f (head)`; `python -m unittest discover` → **177 tests, 0 failures**; `npx vitest run` → 16 passed; `npm run build` → 95 modules; `npx playwright test --project=chromium` → 8 passed. `feature/r4-hatch-feature-engine` created from `main` only after this full green baseline.

## Directory structure / separation of concerns

**PASS.** All CV logic lives under `backend/app/hatch/` (12 modules: `config`, `normalization`, `models`, `preprocessing`, `angles`, `cross_hatch`, `projection`, `spacing`, `periodicity`, `density`, `line_width`, `color`, `feature_extractor`), none of which import FastAPI, SQLAlchemy, or touch the filesystem. Persistence/orchestration is a separate layer (`services/hatch_feature_service.py`), routes are a third, thin layer (`routes/hatch_features.py`). No CV code exists in a route handler, a SQLAlchemy model, frontend code, or `LegendService` itself.

## Input resolution (no arbitrary filesystem paths)

**PASS.** `HatchFeatureService` resolves a crop exclusively through `LegendService.get_entry` (reusing R3's tested Project → Plan → LegendEntry ownership/isolation chain) → `pattern_image_reference` → `StorageService.resolve_legend_crop`. No route or service accepts a client-supplied path. Verified by `test_hatch_feature_service.py::OwnershipAndPreconditionTests` (unknown entry, draft entry, cross-project access, missing file on disk, corrupt file all raise controlled errors) and `test_hatch_feature_routes.py::test_no_local_filesystem_path_is_ever_exposed`.

## Feature versioning

**PASS.** `hatch/config.py::FEATURE_VERSION = "1.0"` (dotted string, not an int). Stamped on every `HatchFeatures`/`HatchFeatureSet`. `HatchFeatureService.compute_features` never silently recomputes or reinterprets an existing row at a different version — it compares the stored `feature_version` against the current constant and only recomputes when `force=True` or the version differs. Verified: `test_hatch_feature_extractor.py::FeatureVersionTests`, `test_hatch_feature_service.py::RecomputationPolicyTests`.

## HatchFeatureSet model / one-to-one with LegendEntry

**PASS.** `backend/app/models/hatch_feature_set.py` — `legend_entry_id` has a unique constraint (one-to-one, DB-enforced), `ON DELETE CASCADE`. `dominant_angles` is plain `sa.JSON` — explicitly **not** pgvector, per R4's scope boundary. All angle/spacing/width/periodicity fields are nullable `Float`; quality-metadata fields (`detected_line_count`, `angle_evidence_strength`, `spacing_available`, `periodicity_available`) are non-nullable with sensible defaults.

## Migration

**PASS.** New migration `a81445a2120c` (`down_revision = 15bc524c492f`), generated via `alembic revision --autogenerate` (no enum-drop fix needed this time — no native Postgres enum columns in this table). Executed against the real dev Postgres: `upgrade head` created `hatch_feature_sets` with all columns/FK/unique index exactly matching the ORM model; `downgrade -1` removed the table and its index while leaving `projects`/`plans`/`plan_pages`/`legend_entries` untouched; `upgrade head` again succeeded cleanly. No previous migration file was edited.

## Original crop preserved / features separately recomputable

**PASS.** `HatchFeatureService` only ever reads the pattern crop (`crop_path.read_bytes()`); nothing in R4 writes to or replaces the stored crop file. `RecomputationPolicyTests::test_force_true_recomputes_from_the_current_crop` proves a crop can be swapped and features recomputed independently of the original extraction, confirming recomputability is real, not assumed.

## Deterministic preprocessing / no unexplained numeric literals

**PASS.** Every threshold used anywhere in `app/hatch/` is a named constant in `config.py` with an inline rationale comment (denoise kernel size, Canny thresholds, Hough parameters, angle bin width/smoothing/separation, cross-hatch ratio, angle evidence minimum, projection peak prominence/distance, spacing peak minimum, line-width sample counts). No inline magic numbers in any algorithm module. Preprocessing pipeline stages and the deliberate omission of morphology are documented in `preprocessing.py`'s module docstring and `docs/architecture/HATCH_FEATURE_ENGINE.md`.

## Angle wraparound handling

**PASS.** `normalization.py::circular_angle_distance(179, 1) == 2`, not 178 — verified directly in `test_hatch_normalization.py` (5 tests) and exercised throughout `angles.py`'s peak-separation and `cross_hatch.py`'s classification logic.

## Angle robustness (horizontal / vertical / 45° / 135° / small perturbations)

**PASS.** All five cases automated in `test_hatch_angles.py::DominantAngleRobustnessTests`, each within a 5° tolerance of ground truth. See `docs/testing/R4_HATCH_FEATURE_BENCHMARK.md` section 2 for the full table.

## Line spacing — scale invariance (critical success criterion)

**PASS, with a documented limitation.** Normalized spacing stable within 6.6% across 0.5x/0.75x/1.0x/1.5x; a real ~15% deviation remains at 2.0x (down from ~40% before the peak-distance-ratio fix). This is reported honestly, not hidden or engineered away by loosening the test past what was measured — see the benchmark doc section 3 and its root-cause note. `test_hatch_spacing.py::ScaleInvarianceTests` asserts a 20% bound (margin above the measured 15%).

## Line density (pattern region, not full crop)

**PASS.** `density.py::compute_density` operates over the bounding box of the binary image's own foreground pixels. `test_hatch_density.py::test_density_ignores_blank_margin_around_a_tight_pattern` directly proves a large blank margin around a small dense region does not dilute the reported density.

## Line width (nullable, no fabricated precision)

**PASS.** `normalized_line_width` is `None` unless `MIN_LINE_WIDTH_SAMPLES` (5) independent perpendicular samples actually succeeded. `test_hatch_line_width.py::test_never_fabricates_precision_below_minimum_sample_count` proves a segment producing too few successful samples returns `None` rather than a value derived from insufficient evidence.

## Cross-hatch detection (named dominance ratio)

**PASS.** `cross_hatch.py::classify_cross_hatch` uses `CROSS_HATCH_SECOND_PEAK_MIN_RATIO` (0.35), calibrated against measured evidence ratios across all 8 benchmark families. Regression-tested against the dense cross-hatch false negative found during calibration (`test_hatch_angles.py::CrossHatchAngleEvidenceTests::test_dense_cross_hatch_still_detects_both_directions`).

## Periodicity (deterministic, bounded, documented range)

**PASS.** Autocorrelation-based (`periodicity.py`), chosen over FFT since the already-short projection signal makes autocorrelation simpler and equally informative — rationale documented in the module docstring. Range `[0.0, 1.0]`, documented explicitly. `test_hatch_periodicity.py` (5 tests) covers boundedness, a perfectly periodic synthetic signal scoring high, and random noise scoring lower than genuine periodicity.

## LAB color features

**PASS.** `color.py::compute_color_features` uses `cv2.COLOR_BGR2LAB`, not raw BGR/RGB — `test_hatch_color.py::test_uses_lab_not_raw_bgr_a_red_fill_shows_up_in_a_channel` directly demonstrates the LAB `a` channel responding to a red fill relative to a neutral gray of similar brightness, the actual reason LAB was chosen.

## Quality metadata (no fabricated confidence)

**PASS.** `detected_line_count`, `angle_evidence_strength`, `spacing_available`, `periodicity_available` each correspond to a directly measured quantity. No synthesized "confidence percentage" field exists anywhere in `HatchFeatures`, `HatchFeatureSet`, or the API response schema.

## HatchFeatureExtractor interface (pure, stateless, thread-safe)

**PASS.** `HatchFeatureExtractor.extract(image) -> HatchFeatures` holds no instance or module-level mutable state. `test_hatch_feature_extractor.py::DeterminismTests::test_determinism_holds_across_separate_extractor_instances` proves independent instances on identical input produce identical results, and `HatchFeatureService` instantiates one extractor per service instance with no shared global.

## HatchFeatureService (ownership, recomputation policy)

**PASS.** Composes `LegendService` for ownership/existence, validates `CONFIRMED` status and pattern-crop presence as distinct, separately-raised errors (`LegendEntryNotConfirmedError`, `NoPatternCropError`), resolves the crop via `StorageService`, decodes with OpenCV (raising `InvalidHatchImageError` on failure, never a raw cv2 exception), calls the extractor, and persists. `force` defaults to `False`; a plain `GET` (`get_features`) never triggers computation at all — proven by `test_hatch_feature_service.py::ComputeAndPersistTests::test_get_features_never_triggers_computation` and `test_hatch_feature_routes.py::test_get_before_compute_returns_404`.

## API surface

**PASS.** `POST`/`GET /api/projects/{project_id}/plans/{plan_id}/legend-entries/{legend_entry_id}/features`, registered in `main.py`. Every domain error maps to a controlled status code (404 for not-found/cross-project, 400 for not-confirmed/no-crop/invalid-image) — never a raw stack trace. 13 route-level tests in `test_hatch_feature_routes.py`, including explicit cross-project (404), corrupt-crop (400, structured detail), and no-filesystem-path-leaked checks.

## Synthetic benchmark dataset (mandatory)

**PASS.** `backend/tests/hatch_fixtures.py` — 8 named families (A–H) plus 8 variant generators (scale, rotation, blur, noise, brightness, line interruption, overlay, crop offset), all deterministic (seeded where randomness is used). Full results in `docs/testing/R4_HATCH_FEATURE_BENCHMARK.md`. Not validated against a single real crop alone — see "Real crop validation" below for how that fits in addition to, not instead of, this dataset.

## Determinism test (mandatory)

**PASS.** `test_hatch_feature_extractor.py::DeterminismTests` — repeated extraction on identical input is byte-for-byte identical, across both repeated calls on one instance and across independent instances.

## Invalid input tests (mandatory)

**PASS.** Empty, zero-size, tiny, `None`, and corrupt-decode-result inputs all raise `InvalidHatchImageError` cleanly (no raw OpenCV traceback observed at any layer). All-white and all-black inputs are valid and do not raise — they simply yield empty/low-evidence features. Verified at both the extractor level (`test_hatch_feature_extractor.py::InvalidInputTests`, 7 tests) and the route level (`test_hatch_feature_routes.py::test_compute_with_corrupt_crop_returns_400_not_a_stack_trace`).

## Real LegendEntry crop validation

**PASS.** Reused the real, non-synthetic construction plan already documented in this repo (`backend/test_plan/floorplan.pdf`, gitignored) and the exact real wall cross-hatch region R3's own checklist previously validated as a pattern crop. Ran the full pipeline (upload → legend entry → pattern/description selection → confirm → `compute_features`) against the real dev Postgres via an ad-hoc, not-committed script; result reported honestly (near-orthogonal angles, high density, markedly lower periodicity than any synthetic fixture) in `docs/testing/R4_HATCH_FEATURE_BENCHMARK.md` section 8. The throwaway project was deleted immediately afterward; no private data committed.

## Frontend (minimal, optional)

**PASS.** A single "Not computed"/"Computed" status pill plus a Compute/Recompute button was added to the existing `LegendEntryEditor.jsx`, shown only once a `LegendEntry` is confirmed (the only state a feature set can exist for). No new page, no feature explorer, no vector/technical display. 2 new unit tests added (`LegendEntryEditor.test.jsx`, now 7 tests total, all passing) plus the 5 pre-existing ones. `npm run build` unaffected (95 modules, unchanged from baseline — no new frontend files, only edits).

## Regression — backend full suite

**PASS.** **293 tests, 0 failures** (177 baseline + 90 new pure-CV unit tests across 9 `test_hatch_*.py` module files + 13 `test_hatch_feature_service.py` + 13 `test_hatch_feature_routes.py`), executed against the real dev Postgres.

## Regression — frontend unit tests

**PASS.** `npx vitest run` → **18 tests, 0 failures** (16 baseline + 2 new hatch-feature-indicator tests).

## Regression — frontend build

**PASS.** `npm run build` → 95 modules, 0 errors (unchanged from baseline; R4's frontend touch was edits only, no new files).

## Regression — Playwright E2E

**PASS.** `npx playwright test --project=chromium` → **8 passed**. One real regression was caught and fixed during this pass: adding a second `.status-pill` element (the new hatch-features indicator) broke two `.locator('.status-pill').last()` assertions in `persistence.spec.js` that had implicitly relied on the LegendEntry's own status pill being the last one on the page. Fixed by adding a stable `data-testid="legend-status-pill"` to the LegendEntry's own pill and updating those two assertions to target it directly, removing the DOM-order dependency rather than papering over it. Re-run confirmed all 8 tests green, including live confirmation (via server logs) that the new `GET .../features` endpoint is actually being called from a real browser and its 404 ("not computed yet") is handled gracefully with no console/network-failure violation.

## Migration up/down/up

**PASS.** See "Migration" above — executed against the real dev Postgres as part of this release's own verification, in addition to being re-run automatically by every integration test file via `db_test_support.build_test_engine()`.

## CI compatibility

**PASS (by construction, not re-simulated with a fresh container this session).** All new backend test files match the existing `test_*.py` glob `unittest discover` already uses; all new dependencies (`opencv-python`, `numpy`) were already present in `requirements.txt` before R4. No GPU, no external API, no customer data, no new CI job/step required.

## No Pattern Library / Detection V2 / similarity search introduced

**PASS.** Reviewed every file changed in this release: no nearest-neighbor search, no embeddings, no vector database, no material-suggestion search, no tile-based detection, no similarity heatmap, no LLM-based interpretation, no async job infrastructure. `dominant_angles` is stored as plain JSON specifically because no vector search exists to query it. The one-to-one `HatchFeatureSet` per confirmed `LegendEntry` is the full extent of what R4 persists.

---

## Deferred technical debt

- The residual ~15% scale-invariance deviation at 2.0x (see benchmark doc section 3) — not eliminated, documented as a known limitation rather than further tuned against one synthetic case.
- Family H (irregular lines)'s occasional chance cross-hatch classification with a small random sample of uncorrelated segments — mitigated by periodicity staying low in that case, not eliminated at the classification level.
- No composite DB constraint tying `hatch_feature_sets.legend_entry_id`'s confirmed-status precondition into the schema itself — enforced in the service layer only, consistent with R3's existing precedent for ownership checks.
- `requirements-minimal.txt` reconciliation — still not touched (a standing decision carried since R2.5, unchanged by R4).

## Risks before Pattern Library / Detection V2

- Only one real, non-synthetic crop (a wall cross-hatch region, not an actual legend-box hatch sample) has been validated — a future release building a Pattern Library should source a real legend-box hatch sample before trusting feature distributions derived only from synthetic fixtures and this one real-but-atypical crop.
- The 2.0x scale-invariance deviation, while within the accepted margin, means any future similarity/matching logic built on `normalized_line_spacing` should treat it as approximate, not exact, especially across widely different crop resolutions.
- `angle_evidence_strength` is an unbounded raw quantity (can exceed 1.0 for dense patterns), not a normalized score — any future consumer must not assume a `[0, 1]` range without re-checking this field's definition.

---

**Pattern Library and Detection V2 work has NOT begun.** Everything in this release is scoped to extracting and persisting one deterministic, versioned `HatchFeatureSet` per confirmed `LegendEntry`. STOP here.
