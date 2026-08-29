import React from 'react'
import { normalizedToDisplayRect } from './coordinates'

const MODE_LABELS = {
  pattern: 'pattern selection',
  description: 'description selection',
  manual_add: 'manual Add region',
  manual_subtract: 'manual Subtract region',
}

/**
 * R9: the plan-image + overlay-drawing surface shared by every stage that
 * needs to show the plan page (Legend, Analysis, Review). Extracted from
 * the old LegendWorkspace.jsx's left column verbatim -- the
 * pointer-selection engine (usePageSelection) and overlay math
 * (normalizedToDisplayRect) are unchanged, only lifted one level so
 * multiple stage components can mount this same canvas instead of one
 * monolithic component owning every stage's UI at once.
 *
 * Overlays are always rendered regardless of which stage is currently
 * active (matches the pre-R9 behavior exactly -- overlays never depended
 * on scroll position/panel visibility before, so no behavior changes).
 */
export default function PlanCanvas({
  pageNumber,
  previewUrl,
  overlays = [],
  detectedRegions = [],
  manualCorrections = [],
  selection,
  toolbar = null,
  hint = null,
}) {
  const draftDisplayRect = selection.draftRect
    ? {
        left: Math.min(selection.draftRect.startX, selection.draftRect.endX),
        top: Math.min(selection.draftRect.startY, selection.draftRect.endY),
        width: Math.abs(selection.draftRect.endX - selection.draftRect.startX),
        height: Math.abs(selection.draftRect.endY - selection.draftRect.startY),
      }
    : null

  return (
    <div className="card panel">
      <strong>Plan Page {pageNumber}</strong>
      <p className="muted">
        {selection.mode
          ? `Drawing ${MODE_LABELS[selection.mode] || selection.mode} -- drag a rectangle on the page.`
          : 'Draw a selection on the plan below when a stage asks for one.'}
      </p>
      <div
        className="plan-stage"
        onMouseDown={selection.onMouseDown}
        onMouseMove={selection.onMouseMove}
        onMouseUp={selection.onMouseUp}
        onMouseLeave={selection.onMouseUp}
        ref={selection.containerRef}
      >
        {/* draggable={false} is load-bearing, not cosmetic: <img> is
            natively draggable by default, and mousedown-then-move on an
            undraggable-unset image makes Chromium hijack the gesture into
            a native OS-level image drag after the first mousemove --
            silently swallowing every mousemove/mouseup our own selection
            handlers need. Found via real Playwright browser testing (a
            curl-only check of the API can never catch this class of bug). */}
        <img
          alt={`Plan page ${pageNumber}`}
          className="plan-image"
          src={previewUrl}
          onLoad={selection.onImageLoad}
          draggable={false}
        />
        {overlays.map((overlay) => {
          const display = normalizedToDisplayRect(overlay.rect, selection.viewSize)
          if (!display) return null
          return (
            <div
              key={overlay.kind}
              className={`plan-overlay overlay-${overlay.kind}`}
              style={{ left: display.left, top: display.top, width: display.width, height: display.height }}
            />
          )
        })}
        {detectedRegions.map((region) => {
          const display = normalizedToDisplayRect(region, selection.viewSize)
          if (!display) return null
          return (
            <div
              key={region.id}
              className={`plan-overlay overlay-detection-${region.status}`}
              style={{ left: display.left, top: display.top, width: display.width, height: display.height }}
            />
          )
        })}
        {manualCorrections.map((correction) => {
          const display = normalizedToDisplayRect(correction, selection.viewSize)
          if (!display) return null
          return (
            <div
              key={correction.id}
              className={`plan-overlay overlay-${correction.correction_type}`}
              style={{ left: display.left, top: display.top, width: display.width, height: display.height }}
              data-testid={`manual-overlay-${correction.correction_type}`}
            />
          )
        })}
        {draftDisplayRect && (
          <div
            className="plan-overlay overlay-draft"
            style={{
              left: draftDisplayRect.left,
              top: draftDisplayRect.top,
              width: draftDisplayRect.width,
              height: draftDisplayRect.height,
            }}
          />
        )}
      </div>
      {toolbar && <div style={{ marginTop: 12 }}>{toolbar}</div>}
      {hint && (
        <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
          {hint}
        </p>
      )}
    </div>
  )
}
