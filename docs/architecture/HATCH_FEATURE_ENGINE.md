# Hatch Feature Engine (R4) — Architecture

Date: 2026-08-27
Scope: a deterministic, versioned computer-vision subsystem that turns a confirmed `LegendEntry`'s stored pattern crop into a persisted `HatchFeatureSet`. This is the **foundation** for a future Pattern Library and Detection V2 — neither is implemented here. No embeddings, no vector search, no ML/neural network, no async job queue, no UI redesign.

## Why this exists

R3 stores a pattern crop for every confirmed `LegendEntry` but never reads it for anything beyond display. R4 is the first release that actually looks at pixel content and extracts measurable, explainable structure from it — the numbers a future material-matching feature would need, computed and persisted now so that work doesn't have to re-derive them later.

## Package layout

```
backend/app/hatch/
  config.py            -- every tunable threshold, named, with rationale
  normalization.py     -- circular (180-degree-periodic) angle arithmetic
  models.py             -- pure dataclasses: AngleEvidence, HatchFeatures
  preprocessing.py      -- validate -> grayscale -> denoise -> binarize -> edges
  angles.py             -- Hough line detection + weighted circular angle histogram
  cross_hatch.py         -- single-direction vs. cross-hatch classification
  projection.py          -- shared rotate-then-project signal (spacing + periodicity)
  spacing.py             -- peak-finding + normalized line spacing
  periodicity.py         -- autocorrelation-based regularity score
  density.py             -- foreground fraction over the pattern's own bounding box
  line_width.py          -- perpendicular thickness sampling along detected lines
  color.py               -- CIELAB color statistics
  feature_extractor.py   -- HatchFeatureExtractor.extract(image) -> HatchFeatures
```

Every module above is pure/stateless and importable in isolation — no FastAPI, no SQLAlchemy, no filesystem access anywhere in `app/hatch/`. This is deliberate: CV logic must remain separately testable, and `HatchFeatureExtractor` must be safe to share across concurrent requests with zero mutable state.

Persistence and orchestration live one layer up, outside `app/hatch/`:

```
backend/app/models/hatch_feature_set.py   -- SQLAlchemy model (one-to-one with LegendEntry)
backend/app/schemas/hatch_feature_set.py  -- Pydantic request/response schemas
backend/app/services/hatch_feature_service.py -- ownership, crop resolution, recompute policy
backend/app/routes/hatch_features.py      -- thin POST/GET routes
```

## Input resolution — no arbitrary filesystem paths

A client never supplies a path. `HatchFeatureService` resolves the crop exclusively through:

```
Project -> Plan -> LegendEntry (via LegendService, ownership-checked) -> pattern_image_reference -> StorageService.resolve_legend_crop()
```

The same `LegendService.get_entry` ownership/isolation chain R3 already tested is reused, not duplicated — a cross-project or cross-plan request 404s before the service ever looks at a feature set.

## Preprocessing pipeline (`preprocessing.py`)

1. **Validate** — reject empty/zero-size/below-`MIN_IMAGE_DIMENSION_PX` input with a controlled `InvalidHatchImageError`, before any OpenCV call that would otherwise raise its own opaque exception.
2. **Grayscale** — structure (angle/spacing/density/line-width) is analyzed in grayscale; color is analyzed separately from the original BGR image, so binarizing for structure never destroys the color signal.
3. **Light Gaussian denoise** (`DENOISE_KERNEL_SIZE = 3`) — absorbs single-pixel scan/compression noise. Deliberately small: hatch lines are themselves only a few pixels wide, so anything more aggressive would blur separate lines together and corrupt spacing/line-width estimation.
4. **Contrast normalization** — stretches the grayscale range to [0, 255] so a crop rendered slightly lighter/darker doesn't shift Otsu's threshold point unpredictably.
5. **Binarization** — Otsu global threshold (`THRESH_BINARY_INV + THRESH_OTSU`). Hatch crops are overwhelmingly bimodal (ink vs. background), which is exactly Otsu's design case, and it is fully deterministic — no tunable threshold to drift. Adaptive thresholding was considered and rejected: no evidence it's needed for vector-rendered PDF previews, and it risks fragmenting long hatch lines.
6. **Morphology — deliberately skipped.** A closing operation large enough to bridge real scan gaps would also risk merging adjacent parallel lines at tight spacing, corrupting the exact measurement it would be introduced to help. Revisit only with real evidence a specific crop family needs it.
7. **Canny edge extraction** — the actual input to Hough line detection.

## Dominant angle extraction (`angles.py`, `normalization.py`)

1. `cv2.HoughLinesP` detects line segments from the Canny edges.
2. Each segment's orientation is normalized into `[0, 180)` — a line has no direction, so 179° and 1° are 2° apart, not 178° apart (`circular_angle_distance`). Every angle comparison anywhere in `hatch/` goes through this function.
3. Segments vote into a weighted circular histogram (weight = segment length, so long confident lines outvote short noise fragments), smoothed with a small circular moving average to absorb bin-edge jitter.
4. The strongest peak is the primary orientation. A second peak counts as a genuine second hatch direction only if it is angularly separated from the first by at least `MIN_PEAK_SEPARATION_DEG` **and** carries at least `CROSS_HATCH_SECOND_PEAK_MIN_RATIO` (0.35) of the primary peak's evidence.
5. If the **winning peak's own evidence** (not the histogram's grand total across all bins — see "Bugs found and fixed" below) falls below `MIN_ANGLE_EVIDENCE_PX`, no angle is reported at all. A crop with insufficient real line structure gets `dominant_angles: []`, `is_cross_hatch: null` — never a fabricated angle.

## Line spacing and periodicity (`projection.py`, `spacing.py`, `periodicity.py`)

Both features share one signal, computed once: `rotate_to_align` rotates the binary image so the primary hatch direction becomes horizontal (expanding the canvas so rotated corners aren't clipped), then `row_projection` sums foreground pixels per row — each hatch line produces one peak.

- **Spacing**: a small numpy-only peak finder (`find_peaks_1d`, non-max-suppression style — deliberately not a new `scipy` dependency) locates line peaks in the projection; the median distance between consecutive peaks is the raw pixel spacing. That raw value is divided by the crop's own diagonal (`normalize_spacing`) so the same physical-looking hatch rendered at a different resolution produces a comparable value. At least `MIN_PEAKS_FOR_SPACING` (2) peaks are required — one peak has no spacing to measure.
- **Periodicity**: autocorrelation of the same projection signal (mean-centered, normalized by its own energy), searching lags between 2% and 50% of the signal length and taking the strongest positive correlation, clipped to `[0.0, 1.0]`. Chosen over an FFT-based periodogram — autocorrelation on this already-short 1D signal is simpler, cheaper, and equally informative for the coarse "how regular is this" answer R4 needs.

## Line density (`density.py`)

Foreground pixel fraction computed over the **bounding box of the binary image's own foreground pixels**, not the full crop. A crop with legitimate blank margin around a tight hatch pattern (very common — a user's drag selection is rarely pixel-perfect) would otherwise report an artificially low density purely from how the selection box happened to be drawn, which has nothing to do with the pattern itself.

## Line width (`line_width.py`)

For each detected Hough segment, samples several interior points (t ∈ [0.2, 0.8] — segment endpoints are the least reliable part of a detected line) and measures the perpendicular run-length of foreground pixels at each sample. The median across all successful samples from all segments is the estimate, normalized by the crop's diagonal. `normalized_line_width` is `None` unless at least `MIN_LINE_WIDTH_SAMPLES` (5) independent samples actually succeeded — no fabricated precision from a handful of lucky hits.

## Color (`color.py`)

CIELAB, not raw BGR — LAB separates lightness (L) from the color-opponent channels (a: green-red, b: blue-yellow), which is far less sensitive to simple brightness/exposure differences between two renders of the same crop than averaging raw color channels directly. Computed on the original color crop, before any binarization.

## Quality metadata

`detected_line_count`, `angle_evidence_strength` (primary peak evidence divided by the crop diagonal), `spacing_available`, `periodicity_available` — every one of these corresponds to a directly measured quantity from the extraction that produced it. There is no synthesized overall "confidence percentage" anywhere in this system.

## Orchestration (`feature_extractor.py`)

`HatchFeatureExtractor.extract(image) -> HatchFeatures` is the single entry point: preprocess once, detect Hough segments once (reused for both angle extraction and line-width estimation — no duplicate Hough transform), then call each feature module in turn. The class holds no state between calls and is safe to share across concurrent requests.

## Persistence (`HatchFeatureSet`, one-to-one with `LegendEntry`)

`legend_entry_id` carries a unique constraint, enforcing one-to-one at the schema level. `dominant_angles` is plain JSON (0–2 floats) — explicitly **not** pgvector or a Postgres array type, per R4's scope boundary; nothing in R4 does vector search. `feature_version` (`"1.0"`, a dotted string) is stamped on every row; a future retune bumps this, and old rows keep whatever version they were computed with rather than being silently reinterpreted.

## Recomputation policy (`HatchFeatureService.compute_features`)

```
compute_features(project_id, plan_id, legend_entry_id, force=False)
```

- Validates ownership (via `LegendService`), that the entry is `CONFIRMED`, and that a pattern crop reference exists — each a distinct, controlled exception mapped to 400/404, never a generic 500.
- If a `HatchFeatureSet` already exists at the current `FEATURE_VERSION` and `force=False`, the existing row is returned unchanged — **no CV work runs**. This is the entire point of the `force` parameter: recomputation is an explicit, intentional action, never a side effect of an ordinary call.
- `GET` (`get_features`) never computes anything — it is a pure read; a `LegendEntry` with no feature set yet simply has nothing to return (404), by design.

## API surface

```
POST /api/projects/{project_id}/plans/{plan_id}/legend-entries/{legend_entry_id}/features   { "force": bool }
GET  /api/projects/{project_id}/plans/{plan_id}/legend-entries/{legend_entry_id}/features
```

No local filesystem path is ever present in a response. `InvalidHatchImageError` (a corrupt or undecodable crop) maps to `400` with a plain description — never a raw OpenCV/numpy stack trace.

## Bugs found and fixed during calibration (see the benchmark doc for full evidence)

1. **Angle-convention mismatch in the synthetic fixture generator** — the "vertical" family builder drew 90°-oriented lines and then rotated by the raw angle parameter, so a nominal 90° request was actually being measured by the extractor as ~1°. Fixed the fixture generator to rotate by `(90 - angle_deg)`, verified empirically against real extractor output rather than assumed from theory.
2. **`MIN_ANGLE_EVIDENCE_PX` checked the histogram's grand total across all 90 angle bins, not the winning peak's own evidence.** A non-hatch dotted control could accumulate enough combined evidence across every bin to pass the old check while no single orientation was actually well-supported. Fixed by checking only the primary peak's own weight, and re-calibrated the threshold (40 → 150) against measured evidence values across all 8 benchmark families.
3. **Dense cross-hatch under-detected one direction.** At tight spacing, crossing lines fragment each other into short segments; the original `HOUGH_MIN_LINE_LENGTH_RATIO` (0.15) filtered too many of them out, systematically starving one direction's evidence. Lowered to 0.05 (with `HOUGH_MAX_LINE_GAP_RATIO` tightened to 0.02 to compensate) after a parameter sweep against the benchmark.
4. **Non-scale-invariant peak-separation distance.** A fixed 2px minimum peak-separation let spurious close sub-peaks corrupt the median spacing estimate at 2x scale. Replaced with a ratio of the crop's own reference dimension (`PROJECTION_PEAK_MIN_DISTANCE_RATIO`), reducing the 2x-scale deviation from ~40% to ~15% (see the benchmark doc — this residual deviation is a documented, accepted limitation, not something engineered away by loosening test thresholds).

## Known limitations (see benchmark doc for full detail)

- Scale invariance is good, not perfect: ~15% worst-case relative deviation in normalized spacing at 2.0x scale.
- With only a handful of random, uncorrelated line segments (the synthetic "irregular lines" control), the angle histogram can occasionally cross the cross-hatch dominance ratio by chance. Periodicity stays low in this case, which is the property that actually matters.
- Line width estimation on a busy real-world crop (dense real hatching, scan noise) is noisier than on clean synthetic fixtures; it is still gated by `MIN_LINE_WIDTH_SAMPLES` so it never fabricates precision from too little evidence.

## Explicitly out of scope for R4

Pattern Library, similarity/nearest-neighbor search, embeddings, vector database, material suggestion, tile-based detection, similarity heatmaps, LLM-based interpretation, async job infrastructure, GPU acceleration, and any UI beyond a minimal computed/not-computed indicator.
