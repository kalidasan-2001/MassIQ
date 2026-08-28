"""Generates the synthetic PDF fixture used by the Playwright E2E suite
(frontend/e2e/fixtures/plan-fixture.pdf). Not run automatically -- the
fixture is committed to git (an explicit .gitignore exception carves out
this one file from the repo's blanket `*.pdf` rule) so E2E runs never
depend on regenerating it, and so its geometry -- and therefore the
normalized selection coordinates every E2E spec hardcodes -- never
silently drifts between runs.

Re-run this script only if the fixture's visual content deliberately needs
to change, then update frontend/e2e/fixtures/fixture-regions.js to match
any coordinate changes.

Usage:
    python scripts/generate_e2e_fixture.py

Deliberately built with the same PyMuPDF primitives as
backend/tests/pdf_fixtures.py (real vector drawing commands + real text),
not a scanned/rastered image -- so the "pattern" region is genuine vector
hatch-like geometry and the "description" region is genuine, crisp,
OCR-friendly text, independent of any raster/scan-quality concerns.
"""

from __future__ import annotations

from pathlib import Path

import fitz

PAGE_WIDTH = 842.0  # landscape A4-ish, matches floorplan.pdf's own orientation
PAGE_HEIGHT = 595.0

# Keep in sync with frontend/e2e/fixtures/fixture-regions.js -- both files
# describe the same fixed, hand-picked normalized (fraction-of-page)
# rectangles so the fixture's geometry and the E2E specs' selection
# coordinates never drift apart silently.
PATTERN_REGION = {"x": 0.12, "y": 0.30, "width": 0.16, "height": 0.20}
DESCRIPTION_REGION = {"x": 0.55, "y": 0.32, "width": 0.30, "height": 0.10}
# R6: a second, independent hatch region -- same pattern, well clear of
# PATTERN_REGION/DESCRIPTION_REGION and the centerlines below -- so
# Detection Engine V2 scanning the whole page has a genuine second real
# target to find alongside the confirmed reference (see
# frontend/e2e/specs/detection-v2.spec.js). Additive only: every existing
# spec's coordinates (PATTERN_REGION/DESCRIPTION_REGION) are unchanged.
SECOND_PATTERN_REGION = {"x": 0.12, "y": 0.62, "width": 0.16, "height": 0.16}


def _draw_hatch_pattern(page: fitz.Page, rect: fitz.Rect) -> None:
    """A real diagonal-line hatch pattern (not a filled block) -- visually
    and structurally similar to the hatch fills used on real construction
    drawings for materials like concrete/masonry.

    Each line lies on y = rect.y1 - (x - x0) for a fixed per-line x0 (a
    true 45-degree line); only the drawn *domain* is clipped to the
    rectangle, both endpoints together, so clipping never distorts the
    slope -- clamping each endpoint independently, without the paired y
    correction, is what produces a fan instead of parallel lines."""
    page.draw_rect(rect, color=(0, 0, 0), width=1)
    step = 8
    x0 = rect.x0 - rect.height
    while x0 < rect.x1:
        px_start = max(x0, rect.x0)
        px_end = min(x0 + rect.height, rect.x1)
        if px_start < px_end:
            py_start = rect.y1 - (px_start - x0)
            py_end = rect.y1 - (px_end - x0)
            page.draw_line(fitz.Point(px_start, py_start), fitz.Point(px_end, py_end), color=(0, 0, 0), width=0.75)
        x0 += step


def build_fixture_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)

    # "Plan-like geometry": an outer wall outline plus a couple of interior
    # partition lines, roughly evoking a simple floor plan.
    page.draw_rect(fitz.Rect(60, 60, PAGE_WIDTH - 60, PAGE_HEIGHT - 100), color=(0, 0, 0), width=2)
    page.draw_line(fitz.Point(60, PAGE_HEIGHT / 2), fitz.Point(PAGE_WIDTH - 60, PAGE_HEIGHT / 2), color=(0, 0, 0), width=1)
    page.draw_line(fitz.Point(PAGE_WIDTH / 2, 60), fitz.Point(PAGE_WIDTH / 2, PAGE_HEIGHT - 100), color=(0, 0, 0), width=1)
    page.insert_text((70, 45), "MassIQ E2E Fixture -- Grundriss (synthetic, safe to commit)", fontsize=11)

    # The selectable hatch-pattern sample.
    pattern_rect = fitz.Rect(
        PATTERN_REGION["x"] * PAGE_WIDTH,
        PATTERN_REGION["y"] * PAGE_HEIGHT,
        (PATTERN_REGION["x"] + PATTERN_REGION["width"]) * PAGE_WIDTH,
        (PATTERN_REGION["y"] + PATTERN_REGION["height"]) * PAGE_HEIGHT,
    )
    _draw_hatch_pattern(page, pattern_rect)

    # A second, independent hatch region (R6) -- same drawing routine, same
    # angle/spacing, just a different location on the page.
    second_pattern_rect = fitz.Rect(
        SECOND_PATTERN_REGION["x"] * PAGE_WIDTH,
        SECOND_PATTERN_REGION["y"] * PAGE_HEIGHT,
        (SECOND_PATTERN_REGION["x"] + SECOND_PATTERN_REGION["width"]) * PAGE_WIDTH,
        (SECOND_PATTERN_REGION["y"] + SECOND_PATTERN_REGION["height"]) * PAGE_HEIGHT,
    )
    _draw_hatch_pattern(page, second_pattern_rect)

    # The selectable legend description text -- legible, OCR-friendly.
    desc_x = DESCRIPTION_REGION["x"] * PAGE_WIDTH
    desc_y = DESCRIPTION_REGION["y"] * PAGE_HEIGHT
    page.draw_rect(
        fitz.Rect(
            desc_x,
            desc_y,
            desc_x + DESCRIPTION_REGION["width"] * PAGE_WIDTH,
            desc_y + DESCRIPTION_REGION["height"] * PAGE_HEIGHT,
        ),
        color=(0.6, 0.6, 0.6),
        width=0.5,
    )
    page.insert_text((desc_x + 8, desc_y + 20), "Stahlbeton C25/30", fontsize=14)
    page.insert_text((desc_x + 8, desc_y + 40), "d=20 cm", fontsize=14)

    data = doc.tobytes()
    doc.close()
    return data


if __name__ == "__main__":
    output_path = Path(__file__).resolve().parents[2] / "frontend" / "e2e" / "fixtures" / "plan-fixture.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(build_fixture_pdf())
    print(f"Wrote {output_path} ({output_path.stat().st_size} bytes)")
