// Single source of truth for plan-fixture.pdf's fixed geometry. Must stay
// in sync with backend/scripts/generate_e2e_fixture.py's PATTERN_REGION /
// DESCRIPTION_REGION constants -- if the fixture is ever regenerated with
// different geometry, update both files together.
//
// These are normalized (fraction-of-page) coordinates, exactly the R3
// coordinate contract (see docs/releases/R3_LEGEND_WORKFLOW_CHECKLIST.md)
// -- independent of viewport size or render DPI, which is what makes them
// safe to hardcode here rather than recompute per test.
module.exports = {
  PATTERN_REGION: { x: 0.12, y: 0.30, width: 0.16, height: 0.20 },
  DESCRIPTION_REGION: { x: 0.55, y: 0.32, width: 0.30, height: 0.10 },
  // R6: a second, independent hatch region elsewhere on the same fixture
  // page -- see backend/scripts/generate_e2e_fixture.py's own comment.
  SECOND_PATTERN_REGION: { x: 0.12, y: 0.62, width: 0.16, height: 0.16 },
  EXPECTED_OCR_SUBSTRING: 'Stahlbeton',
}
