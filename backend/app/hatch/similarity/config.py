"""Centralized, named parameters for the R5 similarity engine -- same
discipline as `app.hatch.config`: every threshold/weight is defined once,
here, with a comment explaining what it controls and why that value was
chosen. See docs/testing/R5_PATTERN_LIBRARY_BENCHMARK.md for the
calibration evidence behind the weights, and
docs/architecture/PATTERN_LIBRARY.md for the full similarity writeup.

Nothing here is a probability or confidence value. Every score this
package produces is a bounded [0.0, 1.0] SIMILARITY -- a measure of
structural/visual resemblance between two HatchFeatureSets, never a
statement about whether a material association is correct.
"""

from __future__ import annotations

# -- Angle similarity ------------------------------------------------------
# Hatch orientation is periodic over 180 degrees (see hatch.normalization),
# so the largest possible circular distance between two angles is exactly
# half the period -- two angles 90 degrees apart (circularly) are as
# different as two angles can be. Used to map a raw circular distance into
# a [0, 1] similarity via a simple linear falloff: similarity = 1 -
# distance / ANGLE_MAX_CIRCULAR_DISTANCE_DEG.
ANGLE_MAX_CIRCULAR_DISTANCE_DEG = 90.0

# -- Cross-hatch agreement ---------------------------------------------
# A clean, maximally explainable component score: 1.0 when both sides
# agree (both single-direction or both cross-hatch), 0.0 when they
# disagree outright. This is NOT the same as "cross-hatch disagreement
# can zero out the overall similarity" -- see combined_similarity.py's
# weighted-average architecture, which is what actually prevents that
# (CROSS_HATCH_WEIGHT is well below 1.0, so a 0.0 component can only drag
# the *renormalized* overall score down by its own weight share, never to
# zero, as long as other components carry evidence).
CROSS_HATCH_AGREEMENT_SCORE = 1.0
CROSS_HATCH_DISAGREEMENT_SCORE = 0.0

# -- Color similarity --------------------------------------------------
# CIE76 Euclidean distance in the same OpenCV 8-bit LAB space
# app.hatch.color already computes features in (L, a, b each roughly
# 0-255, not the textbook 0-100/-128..127 ranges). MAX_LAB_DISTANCE is the
# distance beyond which two crops are considered maximally
# color-dissimilar (mapped to similarity 0.0) -- calibrated empirically
# against actual measured values, not guessed (see
# docs/testing/R5_PATTERN_LIBRARY_BENCHMARK.md's "Color similarity
# calibration" section): the SAME synthetic pattern re-rendered with
# brightness/blur/noise/scale perturbations measured only 0.5-8.5 LAB
# units apart (these are the realistic "same pattern, different scan"
# cases this component must score highly), while measurably different
# hatch families (most driven by ink-coverage/density differences, since
# these fixtures are grayscale ink-on-paper, not true hue variation)
# ranged up to ~125 units apart. 120 sits comfortably above the
# same-pattern noise floor and lets clearly different-density patterns
# fall to a low (not necessarily zero) color similarity.
COLOR_MAX_LAB_DISTANCE = 120.0

# -- Combined similarity weights -----------------------------------------
# Initial weights, in the order R5's own instructions suggest (geometry
# highest, spacing high, periodicity medium-high, density medium,
# cross-hatch medium, line width low-medium, color low) -- NOT copied from
# an unrelated example; chosen to reflect which R4 features carry the most
# reliable structural evidence per the R4 benchmark (angle and spacing are
# the two features with the tightest, most reproducible synthetic-family
# separation; color is the most exposed to scan/brightness variation, see
# hatch/color.py's own docstring). Verified against the R5 ranking
# benchmark as a whole (see docs/testing/R5_PATTERN_LIBRARY_BENCHMARK.md's
# "Weight calibration" section) rather than tuned one test at a time.
ANGLE_WEIGHT = 0.30
SPACING_WEIGHT = 0.20
PERIODICITY_WEIGHT = 0.15
DENSITY_WEIGHT = 0.10
CROSS_HATCH_WEIGHT = 0.10
LINE_WIDTH_WEIGHT = 0.08
COLOR_WEIGHT = 0.07

# -- Qualitative bands (never called "confidence") ------------------------
# Purely descriptive labels for the UI -- documented, not fabricated
# probabilities. A HIGH band is never auto-accepted (see R5 section 23).
HIGH_SIMILARITY_THRESHOLD = 0.75
MEDIUM_SIMILARITY_THRESHOLD = 0.50

# Minimum evidence_coverage (see models.SimilarityResult) required before a
# comparison can be labeled HIGH, regardless of its raw score. Found via
# the R5 ranking benchmark's mandatory negative control (R5 section 33),
# not guessed: querying the non-hatch "dotted noise" control against the
# synthetic benchmark library produced a raw similarity of ~0.84 against
# an unrelated genuine hatch family -- not because the patterns actually
# resembled each other, but because G has no reliable angle/spacing/
# periodicity/cross-hatch evidence at all (see R4's own MIN_ANGLE_EVIDENCE_PX
# gate), leaving only density + color (a combined weight of 0.17 out of
# 1.0, i.e. evidence_coverage=0.17) to determine the entire renormalized
# score. R5 section 19's own renormalize-over-available-features
# instruction is followed exactly for the raw score (never changed here),
# but a comparison this thin should never be labeled to a user as a
# confident HIGH match -- see docs/testing/R5_PATTERN_LIBRARY_BENCHMARK.md's
# "Negative control" section for the full finding. 0.5 (at least half the
# full evidence weight budget) sits above the ~0.17 coverage the negative
# control produced and below what every genuine same-family comparison in
# the benchmark achieved (angle+spacing+periodicity+cross_hatch alone
# already sum to 0.75 of the total weight whenever all four are available).
MIN_COVERAGE_FOR_HIGH_BAND = 0.5

# -- Top-K search ------------------------------------------------------
DEFAULT_TOP_K = 5
