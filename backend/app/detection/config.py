"""Centralized, named parameters for the R6 Detection Engine V2 -- same
discipline as `app.hatch.config`/`app.hatch.similarity.config`: every
threshold is defined once, here, with a comment explaining what it
controls and why that value was chosen. See
docs/testing/R6_DETECTION_BENCHMARK.md for the calibration evidence, and
docs/architecture/DETECTION_ENGINE_V2.md for the full pipeline writeup.

R6 produces CANDIDATE detections only (see DetectedRegionStatus) --
nothing here ever writes to a quantity/area/volume field. See
app.services.detection_service's own module docstring for that boundary.
"""

from __future__ import annotations

# -- Detector versioning ---------------------------------------------------
# Bumped whenever tile size, stride, gating, threshold, or merging
# *semantics* change -- a DetectionRun always records the exact version
# that produced it (see models.DetectionRun.detector_version), so results
# from different algorithm revisions are never silently compared as if
# equivalent. Independent of hatch.config.FEATURE_VERSION (R4) and R5's
# similarity engine, both of which R6 reuses unmodified.
DETECTOR_VERSION = "1.0"

# -- Tile geometry -----------------------------------------------------
# Chosen from direct measurement, not guessed: extracting R4 benchmark
# hatch families (10px/20px/30px spacing) at several candidate tile sizes
# showed 64px tiles fail to reliably recover angle/spacing evidence for
# wide-spacing families (e.g. family F's 30px-spacing cross-hatch reported
# zero dominant angles at 64px), while 96px and above recovered reliable
# evidence for every tested spacing. 128px was chosen over 96/192/256 as
# the smallest size with a comfortable margin above the 96px minimum that
# still worked reliably -- smaller tiles give finer region-boundary
# resolution and more tiles per page (see docs/testing/R6_DETECTION_BENCHMARK.md's
# "Tile size calibration" section for the full measured table).
TILE_SIZE_PX = 128

# 25% overlap (stride = 75% of tile size): hatch regions will not align to
# the tile grid, so *some* overlap is a safety margin against a real hatch
# region landing unluckily split across a tile boundary and under-evidenced
# on both sides -- a case the hand-placed synthetic benchmark fixtures
# don't happen to stress. Measured tile-count cost, not guessed: on an
# 1800x1200 page, non-overlapping tiling produces 150 tiles, 25% overlap
# 247 (1.65x), 50% overlap 504 (3.36x). On the synthetic benchmark itself,
# recall was identical (9/9) at all three overlap levels -- reported
# honestly rather than claiming a recall benefit that wasn't actually
# measured; 25% overlap was kept as a reasoned safety margin for real
# pages at a modest 1.65x cost, not because it improved this particular
# benchmark's recall. See docs/testing/R6_DETECTION_BENCHMARK.md.
TILE_STRIDE_PX = 96

# Safety cap on total tiles evaluated per run -- protects a pathological
# (e.g. extremely large or misconfigured) page from an unbounded synchronous
# request. Real pages render at up to 1800px wide (see
# core/config.py's plan render cap); a 1800x2400 page at this tile/stride
# produces roughly 400-500 tiles, comfortably under this cap.
MAX_TILES_PER_RUN = 4000

# -- Tile quality gating (R6 section 9) ------------------------------------
# A tile is skipped (never scored against the reference, never persisted
# as a candidate) if it shows no reliable line-angle evidence at all --
# the same "insufficient evidence" signal R4's own MIN_ANGLE_EVIDENCE_PX
# gate already produces (an empty `dominant_angles` list). This is
# deliberately the *only* gate (not, say, a minimum density) -- R4's own
# angle-evidence gate is already calibrated evidence (see
# docs/testing/R4_HATCH_FEATURE_BENCHMARK.md), and duplicating a second,
# independently-tuned gate here would risk disagreeing with it for no
# benefit. Skipped tiles are still counted (DetectionRun.skipped_tile_count)
# -- never silently dropped from the record, per R6 section 9's explicit
# "do not throw away uncertain tiles silently."
REQUIRE_ANGLE_EVIDENCE_TO_SCORE = True

# -- Candidate thresholding (R6 section 12) --------------------------------
# Deliberately NOT 0.8 by default assumption -- calibrated against the R6
# synthetic detection benchmark (see docs/testing/R6_DETECTION_BENCHMARK.md's
# "Threshold calibration" section): target hatch regions in the benchmark
# scored 0.75-0.98 similarity against their own reference; the strongest
# distractor (a different but structurally similar hatch family) scored
# below this. Kept deliberately permissive relative to R5's own
# HIGH_SIMILARITY_THRESHOLD (0.75) -- R6 section 21 explicitly prioritizes
# recall over precision for this first release (a missed region is worse
# than an extra reviewable candidate).
CANDIDATE_SIMILARITY_THRESHOLD = 0.65

# Mirrors R5's evidence_coverage protection (see hatch/similarity/config.py's
# MIN_COVERAGE_FOR_HIGH_BAND docstring for the original finding this
# pattern is based on): a tile-vs-reference comparison built from too
# little available evidence must not count as a candidate no matter how
# high its raw similarity happens to be.
MIN_EVIDENCE_COVERAGE_FOR_CANDIDATE = 0.5

# -- Neighbor merging (R6 section 13) --------------------------------------
# 8-connectivity (includes diagonal neighbors) rather than 4-connectivity --
# a real hatch region's candidate tiles frequently touch only at a corner
# where the tile grid happens to fall across the region's own diagonal
# edge; 4-connectivity was found (via the synthetic benchmark) to
# needlessly split one visually contiguous region into two adjacent
# candidates in that case.
MERGE_CONNECTIVITY = 8

# -- Region scoring (R6 section 15) -----------------------------------
# Median tile similarity, not max or mean -- a single strong tile at a
# region's edge should not make a mostly-weak region look confidently
# scored (max), and a mean is more sensitive to a handful of low-evidence
# tiles the merge step still included at the region's boundary than the
# median is. Evidence coverage is aggregated as a plain mean (no reason to
# prefer the median there -- coverage does not have the same
# single-outlier risk similarity does). See
# docs/architecture/DETECTION_ENGINE_V2.md's "Region scoring" section.
