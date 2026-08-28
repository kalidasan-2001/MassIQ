"""Centralized, named constants for R7's geometry/quantity engine -- same
discipline as app.hatch.config/app.detection.config: every constant is
defined once, here, with a comment explaining what it controls.
"""

from __future__ import annotations

# Bumped whenever the union/subtraction algorithm, rounding, or overall
# quantity formula *semantics* change -- every QuantityResult records the
# exact version that produced it (see models.QuantityResult.calculation_version),
# so a future formula change is never silently compared against an older
# result as if equivalent. Independent of R6's DETECTOR_VERSION.
CALCULATION_VERSION = "1.0"

# 1 PDF point (1/72 inch) in meters -- used only by the DECLARED_SCALE
# scale method (see models.plan_scale.PlanScale's docstring for the full
# "why" of this conversion and its documented assumption that the plan
# was exported at 100% print scale).
POINTS_PER_INCH = 72.0
METERS_PER_INCH = 0.0254
POINTS_TO_METERS = METERS_PER_INCH / POINTS_PER_INCH
