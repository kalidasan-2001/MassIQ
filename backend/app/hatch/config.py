"""Centralized, named algorithm parameters for the Hatch Feature Engine.

R4's own instructions are explicit: "No unexplained numeric literals
scattered across functions." Every threshold used anywhere in
`backend/app/hatch/` is defined here, once, with a comment explaining what
it controls and why that rough magnitude was chosen. Nothing here is
tuned against a single real crop -- see
docs/testing/R4_HATCH_FEATURE_BENCHMARK.md for the synthetic-benchmark
evidence behind these choices, and
docs/architecture/HATCH_FEATURE_ENGINE.md for the full algorithm writeup.
"""

from __future__ import annotations

# -- Feature versioning -------------------------------------------------
# Bumped whenever the *semantics* of any extracted feature change (not for
# pure refactors). Old HatchFeatureSet rows keep whatever version they were
# computed with -- see HATCH_FEATURE_ENGINE.md's "Feature versioning"
# section. A dotted string, not an int, so a future "1.1" (minor parameter
# retune, still comparable) can be distinguished from a "2.0" (semantics
# changed, not directly comparable).
FEATURE_VERSION = "1.0"

# -- Input validation -----------------------------------------------------
# Below this, a crop is too small to contain enough hatch-line structure
# for any of the geometric measurements to be meaningful -- reject early
# with a controlled error rather than let downstream stages silently
# produce noise dressed up as a real measurement.
MIN_IMAGE_DIMENSION_PX = 8

# -- Preprocessing ----------------------------------------------------------
# Odd kernel size for a light Gaussian blur before edge detection. Hatch
# lines are typically 1-3px wide at the resolutions this app renders
# previews at (see core/config.py's plan_render_dpi); a kernel much larger
# than this would blur separate lines together and corrupt spacing
# estimation, so this stays deliberately small -- its only job is to
# smooth single-pixel scan/compression noise, not to denoise aggressively.
DENOISE_KERNEL_SIZE = 3

# Canny edge detector thresholds. These are the traditional "low:high
# should be roughly 1:2 to 1:3" ratio Canny's own author recommended, at a
# level that reliably fires on real ink-on-paper/vector line contrast
# without also firing heavily on JPEG-compression ringing.
CANNY_LOW_THRESHOLD = 50
CANNY_HIGH_THRESHOLD = 150

# -- Hough line detection --------------------------------------------------
HOUGH_RHO_RESOLUTION_PX = 1.0
HOUGH_THETA_RESOLUTION_RAD_DIVISOR = 180  # pi / this = radians per bin
HOUGH_VOTE_THRESHOLD = 20
# Both expressed as a fraction of min(width, height) so they scale with
# the crop instead of being tied to one specific pixel size. Tuned against
# the synthetic benchmark, not guessed: an initial, stricter
# minLineLength (0.15) worked fine for single-direction and moderately
# spaced cross-hatch, but systematically under-detected one of the two
# directions in *dense* cross-hatch (tight spacing + crossing lines
# fragment each line into shorter segments between intersections than a
# 0.15-ratio minimum allowed through) -- a real false negative caught by
# the benchmark, not a hypothetical. Lowering to 0.05 (with a
# correspondingly tighter max gap so short, noisy fragments don't get
# bridged into false long lines) recovered correct cross-hatch detection
# for the dense family while leaving every other family's results the
# same or better. See docs/testing/R4_HATCH_FEATURE_BENCHMARK.md.
HOUGH_MIN_LINE_LENGTH_RATIO = 0.05
HOUGH_MAX_LINE_GAP_RATIO = 0.02

# -- Angle histogram ---------------------------------------------------
# Hatch orientation is periodic over 180 degrees (a line and its 180-degree
# rotation are the same line) -- see normalization.py's circular_angle_distance.
ANGLE_PERIOD_DEG = 180.0
ANGLE_BIN_WIDTH_DEG = 2.0
ANGLE_BIN_COUNT = int(ANGLE_PERIOD_DEG / ANGLE_BIN_WIDTH_DEG)
# Circular moving-average smoothing window (in bins) applied to the raw
# weighted angle histogram before peak-finding -- absorbs bin-boundary
# jitter (a real 45.0 degree line landing exactly on a bin edge) without
# smearing genuinely distinct orientations into each other.
ANGLE_SMOOTHING_WINDOW_BINS = 3
# Two peaks closer than this (circular distance) are treated as the same
# orientation's shoulder, not two separate hatch directions.
MIN_PEAK_SEPARATION_DEG = 20.0
# A second peak must carry at least this fraction of the primary peak's
# evidence to count as a genuine second hatch direction (R4 section 15's
# "second orientation must exceed a meaningful fraction of first").
# Chosen from the synthetic benchmark: real cross-hatch families produced
# a second-peak ratio around 0.8-1.0 (both directions drawn with equal
# weight); single-direction families' strongest secondary bin never
# exceeded ~0.15. 0.35 sits with a wide margin between the two.
CROSS_HATCH_SECOND_PEAK_MIN_RATIO = 0.35
# Below this much total weighted line evidence (sum of contributing line
# lengths, in pixels), angle detection is considered unreliable and a
# missing (None) angle is reported rather than a fabricated one. Tuned
# against the synthetic benchmark (docs/testing/R4_HATCH_FEATURE_BENCHMARK.md),
# not a guess: the non-hatch dotted control produced ~85-90px of spurious
# evidence purely from randomly-collinear dots bridging within Hough's own
# gap tolerance, the irregular-line control produced ~300-320px (real
# lines, just not a periodic hatch), and every genuine hatch family
# produced 1200px or more. 150 sits with a wide margin above the dotted
# control's false-positive evidence and a wide margin below every real
# hatch family's evidence, while still allowing the irregular-line control
# through (deliberately -- it contains real detectable lines; periodicity
# and cross-hatch dominance, not this threshold, are what should flag it
# as non-periodic).
MIN_ANGLE_EVIDENCE_PX = 150.0

# -- Line spacing / periodicity (shared projection-based pipeline) ------
# Minimum prominence (as a fraction of the projection signal's own
# peak-to-peak range) for a local maximum to count as a real hatch-line
# peak rather than sensor/quantization noise in the projection signal.
PROJECTION_PEAK_MIN_PROMINENCE_RATIO = 0.15
# A local maximum must also be separated from its neighbors by at least
# this fraction of the crop's own diagonal (in the rotated projection) to
# avoid counting the same physical line's shoulder twice -- expressed as a
# ratio, not a fixed pixel count, specifically because a *fixed* small
# pixel distance (2px was the original, naive choice) does not scale with
# resolution: the benchmark's 2x-scale variant of a normal parallel-line
# family showed real lines fragmenting into multiple close sub-peaks a
# fixed 2px filter no longer suppressed, corrupting the median spacing
# estimate. A ratio-based minimum distance (with a small absolute floor
# for tiny crops) scales correctly instead. See
# docs/testing/R4_HATCH_FEATURE_BENCHMARK.md's scale-invariance results.
PROJECTION_PEAK_MIN_DISTANCE_RATIO = 0.01
PROJECTION_PEAK_MIN_DISTANCE_FLOOR_PX = 2
# At least this many detected peaks are required to report a spacing
# value at all -- a single peak has no "spacing between peaks" to measure.
MIN_PEAKS_FOR_SPACING = 2

# -- Line width ----------------------------------------------------------
# Number of sample points taken along each contributing Hough line segment
# to estimate local thickness (perpendicular run-length of foreground
# pixels). More samples -> smoother median, at proportional cost; this is
# a light, fixed budget appropriate for interactive use (see R4 section 36).
LINE_WIDTH_SAMPLES_PER_LINE = 5
# At least this many individual thickness samples must succeed (hit real
# foreground on both sides) before a normalized_line_width is reported at
# all -- otherwise None, per R4 section 14's "do not fabricate precision".
MIN_LINE_WIDTH_SAMPLES = 5

# -- Density ---------------------------------------------------------------
# Density is computed over the bounding box of detected foreground
# structure, not the full (possibly mostly-blank-margin) crop -- see
# HATCH_FEATURE_ENGINE.md's "Density" section for why.
