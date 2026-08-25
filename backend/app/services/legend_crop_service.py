from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

from app.models.plan_page import PlanPage
from app.services.storage_service import StorageService

# Tolerance for floating-point normalized-coordinate accumulation
# (frontend division, JSON round-trip) -- selections that land at exactly
# 1.0 + a few ULPs must not be rejected as "out of bounds".
_BOUNDS_EPSILON = 1e-6


class CropBoundsError(ValueError):
    """Raised for a selection that is negative, zero-size, or extends past
    the page. Callers (routes) must map this to a 4xx, never a 500."""


@dataclass(frozen=True)
class RegionSelection:
    """Normalized page-fraction coordinates in [0, 1] -- see the R3
    coordinate contract (docs/releases/R3_LEGEND_WORKFLOW_CHECKLIST.md).
    Never DOM/screen pixels, never absolute image pixels either -- pixel
    conversion happens only inside crop_region, against the *current* real
    file dimensions.

    Validated on construction so this class is self-defending regardless of
    whether the caller is the Pydantic-guarded HTTP route or a direct
    service/test call.
    """

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise CropBoundsError("Selection must have a positive width and height")
        if self.x < 0 or self.y < 0:
            raise CropBoundsError("Selection coordinates cannot be negative")
        if self.x + self.width > 1.0 + _BOUNDS_EPSILON or self.y + self.height > 1.0 + _BOUNDS_EPSILON:
            raise CropBoundsError("Selection extends beyond the page bounds")


class LegendCropService:
    """Focused crop capability for R3. Resolves a PlanPage's preview
    through StorageService, converts a normalized RegionSelection to pixel
    coordinates using the *actual current* preview file's own dimensions
    (never a client-supplied or cached size), and returns PNG bytes.
    Storing the result is StorageService's job (LegendService wires the
    two together) -- this class never writes to disk itself, and never
    touches FastAPI."""

    def __init__(self, storage: StorageService | None = None):
        self._storage = storage or StorageService()

    def crop_region(self, plan_page: PlanPage, selection: RegionSelection) -> bytes:
        if not plan_page.preview_reference:
            raise CropBoundsError("This page has no rendered preview to crop")
        preview_path = self._storage.resolve_preview(plan_page.preview_reference)

        with Image.open(preview_path) as image:
            width, height = image.size
            x0 = round(selection.x * width)
            y0 = round(selection.y * height)
            x1 = round((selection.x + selection.width) * width)
            y1 = round((selection.y + selection.height) * height)
            # Clamp only the upper bound against float rounding at the
            # image edge -- __post_init__ already rejected anything
            # meaningfully out of bounds.
            x1 = min(x1, width)
            y1 = min(y1, height)
            if x1 <= x0 or y1 <= y0:
                raise CropBoundsError("Selection is too small to crop at this image's resolution")

            crop = image.convert("RGB").crop((x0, y0, x1, y1))
            buffer = io.BytesIO()
            crop.save(buffer, format="PNG")
            return buffer.getvalue()
