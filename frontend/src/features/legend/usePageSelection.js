import { useEffect, useRef, useState } from 'react'
import { draftToNormalizedRect } from './coordinates'

/**
 * Generalized version of PlanViewer.jsx's drag-rectangle selection logic
 * (toRectFromDraft + the begin/move/end mouse handlers), extracted so the
 * Legend workflow doesn't grow PlanViewer.jsx itself. Mode-based
 * ('pattern' | 'description' | null) rather than PlanViewer's many
 * hardcoded modes, since the Legend workflow only ever needs these two
 * selections.
 *
 * `onRegionComplete(mode, normalizedRect)` fires once a drag finishes and
 * produces a normalized rect (see coordinates.js) -- never DOM pixels.
 */
export function usePageSelection(onRegionComplete) {
  const containerRef = useRef(null)
  const imgRef = useRef(null)
  const modeRef = useRef(null)
  const draftRef = useRef(null)

  const [mode, setMode] = useState(null)
  const [naturalSize, setNaturalSize] = useState({ width: 0, height: 0 })
  const [viewSize, setViewSize] = useState({ width: 0, height: 0 })
  const [draftRect, setDraftRect] = useState(null)

  // R7: `viewSize` must track the image's actual rendered size for the
  // lifetime of the component, not just its size at the moment `onLoad`
  // fired -- every overlay on the page (pattern/description/detection/
  // manual-correction) is positioned from `normalizedToDisplayRect(rect,
  // viewSize)`, and a stale viewSize after a browser window resize makes
  // every overlay visibly drift away from the plan image underneath it.
  // Found via a real Playwright browser resize (see
  // e2e/specs/review-quantity.spec.js's coordinate-resilience check) --
  // exactly the class of bug a curl-only/component-only test cannot catch,
  // the same lesson the R3 native-image-drag bug already taught.
  useEffect(() => {
    const img = imgRef.current
    if (!img || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(() => {
      setViewSize({ width: img.clientWidth, height: img.clientHeight })
    })
    observer.observe(img)
    return () => observer.disconnect()
    // Re-attach once the image identity/natural size actually changes
    // (a new preview loaded) -- imgRef.current is set synchronously in
    // onImageLoad before this effect's dependency changes trigger a rerun.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [naturalSize.width, naturalSize.height])

  const startMode = (nextMode) => {
    modeRef.current = nextMode
    setMode(nextMode)
  }

  const cancelMode = () => {
    modeRef.current = null
    draftRef.current = null
    setMode(null)
    setDraftRect(null)
  }

  const onImageLoad = (event) => {
    const img = event.currentTarget
    imgRef.current = img
    setNaturalSize({ width: img.naturalWidth, height: img.naturalHeight })
    setViewSize({ width: img.clientWidth, height: img.clientHeight })
  }

  const getPoint = (event) => {
    if (!containerRef.current) return null
    const rect = containerRef.current.getBoundingClientRect()
    return {
      x: Math.max(0, Math.min(rect.width, event.clientX - rect.left)),
      y: Math.max(0, Math.min(rect.height, event.clientY - rect.top)),
    }
  }

  const onMouseDown = (event) => {
    if (!modeRef.current) return
    const point = getPoint(event)
    if (!point) return
    const next = { startX: point.x, startY: point.y, endX: point.x, endY: point.y }
    draftRef.current = next
    setDraftRect(next)
  }

  const onMouseMove = (event) => {
    if (!draftRef.current) return
    const point = getPoint(event)
    if (!point) return
    const next = { ...draftRef.current, endX: point.x, endY: point.y }
    draftRef.current = next
    setDraftRect(next)
  }

  const onMouseUp = () => {
    const activeMode = modeRef.current
    const draft = draftRef.current
    draftRef.current = null
    setDraftRect(null)
    modeRef.current = null
    setMode(null)
    if (!activeMode || !draft) return
    const normalized = draftToNormalizedRect(draft, naturalSize, viewSize)
    if (normalized) onRegionComplete?.(activeMode, normalized)
  }

  return {
    containerRef,
    mode,
    naturalSize,
    viewSize,
    draftRect,
    startMode,
    cancelMode,
    onImageLoad,
    onMouseDown,
    onMouseMove,
    onMouseUp,
  }
}
