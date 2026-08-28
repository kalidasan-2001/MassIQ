"""Boolean geometry for R7's quantity engine (release-critical -- R7
section 12). Accepted DetectedRegions may overlap each other and manual
ADD corrections; manual SUBTRACT corrections may overlap each other and
the positive geometry. Naive scalar area summation (what the legacy
`quantityEngine.js` does -- see docs/architecture/REVIEW_AND_QUANTITY_ENGINE.md's
audit section) silently double-counts/double-subtracts in every one of
those cases, so this module always computes a real geometric union before
measuring area.

Dependency decision (R7 section 12): Shapely was already present in this
project's dependency tree as a transitive dependency of
`rapidocr-onnxruntime` (R3), confirmed via `pip show shapely`. Rather than
hand-roll rectangle-union/subtraction math (explicitly discouraged) or add
a brand-new dependency, R7 pins the already-resolved version explicitly in
requirements.txt and uses it directly -- a mature, widely-used library is
exactly what R7 section 12 asks for, and no new supply-chain surface is
introduced since every environment that already installs requirements.txt
(including CI) already resolves this package today.

All boolean operations happen in real physical units (meters), not raw
normalized [0,1] fractions -- a page is not generally square, so
multiplying a normalized-area fraction by one scalar constant would be
wrong; x and y each need their own page-dimension scale factor applied
BEFORE any union/difference, so that Shapely's own `.area` is already a
true, correctly-scaled square-meter measurement with no further per-axis
correction needed.
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import box as shapely_box
from shapely.ops import unary_union


@dataclass(frozen=True)
class NormalizedRect:
    """A plain rectangle in the same normalized [0,1] page-fraction
    coordinate contract every other overlay in this app uses (R7 section
    9) -- x/y/width/height, never DOM/screen pixels."""

    x: float
    y: float
    width: float
    height: float


def _rect_to_meter_polygon(
    rect: NormalizedRect,
    page_width_points: float,
    page_height_points: float,
    real_meters_per_plan_point: float,
):
    """Converts one normalized rect into a Shapely polygon in real-world
    meter coordinates. page_width_points/page_height_points come from the
    PlanPage's own persisted PDF-point geometry (never re-derived from a
    rendered preview's pixel size, which can change with DPI settings)."""
    x0 = rect.x * page_width_points * real_meters_per_plan_point
    y0 = rect.y * page_height_points * real_meters_per_plan_point
    x1 = (rect.x + rect.width) * page_width_points * real_meters_per_plan_point
    y1 = (rect.y + rect.height) * page_height_points * real_meters_per_plan_point
    return shapely_box(x0, y0, x1, y1)


def compute_final_area_m2(
    positive_rects: list[NormalizedRect],
    negative_rects: list[NormalizedRect],
    page_width_points: float,
    page_height_points: float,
    real_meters_per_plan_point: float,
) -> float:
    """FinalGeometry = union(positive_rects) - union(negative_rects);
    FinalArea = area(FinalGeometry), in square meters (R7 section 2).

    - No positive geometry at all -> 0.0 (never an error, never NaN).
    - Overlapping positive rects -> counted once (union), never double
      counted.
    - Overlapping negative rects -> unioned before subtracting, so an
      overlapping pair of SUBTRACT corrections does not double-remove the
      shared area.
    - A SUBTRACT rect (or union of them) that extends beyond the positive
      geometry, or entirely covers it -> only the actually-intersecting
      part is removed; the result is clamped to >= 0.0, never negative.
    """
    if not positive_rects:
        return 0.0

    positive_polygons = [
        _rect_to_meter_polygon(rect, page_width_points, page_height_points, real_meters_per_plan_point)
        for rect in positive_rects
    ]
    positive_union = unary_union(positive_polygons)

    if negative_rects:
        negative_polygons = [
            _rect_to_meter_polygon(rect, page_width_points, page_height_points, real_meters_per_plan_point)
            for rect in negative_rects
        ]
        negative_union = unary_union(negative_polygons)
        final_geometry = positive_union.difference(negative_union)
    else:
        final_geometry = positive_union

    # Defensive clamp: a valid Shapely polygon's .area is already >= 0 and
    # finite, but this makes the "never negative, never NaN/Infinity"
    # contract (R7 section 22) explicit and independent of Shapely's own
    # internal guarantees ever changing.
    area = final_geometry.area
    if area != area or area in (float("inf"), float("-inf")):  # NaN/Infinity guard
        return 0.0
    return max(0.0, area)
