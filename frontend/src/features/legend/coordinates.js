// R3 coordinate contract: the ONLY authoritative representation of a
// selection is a normalized page-fraction rect, { x, y, width, height },
// each in [0, 1], relative to the persisted preview image's own natural
// pixel dimensions (naturalWidth/naturalHeight -- i.e. the exact PNG
// StorageService persisted, "rendered_page_width/height"). This is what
// gets sent to the backend and is what LegendCropService expects.
//
// It is deliberately NOT screen/DOM pixels and NOT even absolute natural
// pixels -- normalizing removes both the browser-window/display-size
// dependency (view size never appears in the stored value) and the
// render-DPI dependency (a future re-render at a different DPI still
// yields the same fraction of the same page). See
// docs/releases/R3_LEGEND_WORKFLOW_CHECKLIST.md.
//
// Pure functions only -- no DOM access -- so this module is directly
// unit-testable (coordinates.test.js) without a browser environment.

const MIN_DRAFT_PIXELS = 3

function clampNormalized(rect) {
  const x = Math.max(0, Math.min(1, rect.x))
  const y = Math.max(0, Math.min(1, rect.y))
  const width = Math.max(0, Math.min(1 - x, rect.width))
  const height = Math.max(0, Math.min(1 - y, rect.height))
  return { x, y, width, height }
}

/**
 * Converts an in-progress mouse-drag rectangle (DOM/view pixel space,
 * { startX, startY, endX, endY }) into a normalized page-fraction rect.
 * Returns null if any required size is missing/zero, or if the resulting
 * drag is smaller than a sane minimum (matches PlanViewer's existing
 * toRectFromDraft threshold, applied here in view-pixel space before
 * normalizing).
 */
export function draftToNormalizedRect(draft, naturalSize, viewSize) {
  if (!draft || !naturalSize?.width || !naturalSize?.height || !viewSize?.width || !viewSize?.height) return null

  const viewX = Math.min(draft.startX, draft.endX)
  const viewY = Math.min(draft.startY, draft.endY)
  const viewW = Math.abs(draft.endX - draft.startX)
  const viewH = Math.abs(draft.endY - draft.startY)
  if (viewW < MIN_DRAFT_PIXELS || viewH < MIN_DRAFT_PIXELS) return null

  const scaleX = naturalSize.width / viewSize.width
  const scaleY = naturalSize.height / viewSize.height

  return clampNormalized({
    x: (viewX * scaleX) / naturalSize.width,
    y: (viewY * scaleY) / naturalSize.height,
    width: (viewW * scaleX) / naturalSize.width,
    height: (viewH * scaleY) / naturalSize.height,
  })
}

/**
 * Converts a normalized rect back into display-space pixels for drawing an
 * overlay -- deliberately takes ONLY viewSize, not naturalSize. That's the
 * whole point of normalizing: the same stored selection renders correctly
 * at any displayed preview size without knowing anything about natural
 * pixel dimensions or render DPI.
 */
export function normalizedToDisplayRect(normRect, viewSize) {
  if (!normRect || !viewSize?.width || !viewSize?.height) return null
  return {
    left: normRect.x * viewSize.width,
    top: normRect.y * viewSize.height,
    width: normRect.width * viewSize.width,
    height: normRect.height * viewSize.height,
  }
}
