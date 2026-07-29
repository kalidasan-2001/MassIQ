import React, { useMemo, useRef, useState } from 'react'
import ExportButton from './ExportButton'
import HatchDetectionPanel from './HatchDetectionPanel'
import DetectionReviewPanel from './DetectionReviewPanel'
import LegendAssistantPanel from './LegendAssistantPanel'
import RegionEditor from './RegionEditor'
import SectionHeightPanel from './SectionHeightPanel'
import { buildQuantityResult } from '../utils/quantityEngine'

const COMPONENT_NAME = 'Stahlbeton C25/30'
const CLICK_SAMPLE_SIZE = 40
const CLICK_CORRECTION_SIZE = 80
const MIN_SAMPLE_SIZE = 5
const MOVE_STEP = 8

const round = (value, decimals = 2) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  const factor = 10 ** decimals
  return Math.round(Number(value) * factor) / factor
}

const areaFromRect = (rect) => Math.max(0, Number(rect?.w || 0)) * Math.max(0, Number(rect?.h || 0))

const correctionCount = (region) => Math.max(1, Math.round(Number(region?.count) || 1))

const correctionLineTotalM2 = (region) => Number(region?.area_m2 || 0) * correctionCount(region)

const clampBoxToImage = (box, naturalSize) => {
  if (!box || !naturalSize.width || !naturalSize.height) return null
  const width = Math.max(1, Math.min(naturalSize.width, Math.round(box.w)))
  const height = Math.max(1, Math.min(naturalSize.height, Math.round(box.h)))
  const x = Math.max(0, Math.min(naturalSize.width - width, Math.round(box.x)))
  const y = Math.max(0, Math.min(naturalSize.height - height, Math.round(box.y)))
  return { x, y, w: width, h: height }
}

const toRectFromDraft = (draft, naturalSize, viewSize) => {
  if (!draft || !naturalSize.width || !naturalSize.height || !viewSize.width || !viewSize.height) return null
  const scaleX = naturalSize.width / viewSize.width
  const scaleY = naturalSize.height / viewSize.height
  const x = Math.min(draft.startX, draft.endX)
  const y = Math.min(draft.startY, draft.endY)
  const w = Math.abs(draft.endX - draft.startX)
  const h = Math.abs(draft.endY - draft.startY)
  if (w < 3 || h < 3) return null
  return clampBoxToImage(
    {
      x: x * scaleX,
      y: y * scaleY,
      w: w * scaleX,
      h: h * scaleY,
    },
    naturalSize
  )
}

const toDisplayRect = (rect, naturalSize, viewSize) => {
  if (!rect || !naturalSize.width || !naturalSize.height || !viewSize.width || !viewSize.height) return null
  return {
    left: (rect.x / naturalSize.width) * viewSize.width,
    top: (rect.y / naturalSize.height) * viewSize.height,
    width: (rect.w / naturalSize.width) * viewSize.width,
    height: (rect.h / naturalSize.height) * viewSize.height,
  }
}

export default function PlanViewer({ file_id, page_image_url, backendBase = 'http://127.0.0.1:8010' }) {
  const containerRef = useRef(null)
  const selectionModeRef = useRef(null)
  const draftRectRef = useRef(null)
  const [projectName, setProjectName] = useState('New Project')
  const [realDistance, setRealDistance] = useState('10')
  const [pixelDistance, setPixelDistance] = useState(1000)
  const [scale, setScale] = useState(null)
  const [naturalSize, setNaturalSize] = useState({ width: 0, height: 0 })
  const [viewSize, setViewSize] = useState({ width: 0, height: 0 })
  const [selectionMode, setSelectionMode] = useState(null)
  const [draftRect, setDraftRect] = useState(null)
  const [legendBox, setLegendBox] = useState(null)
  const [hatchBox, setHatchBox] = useState(null)
  const [hatchSample, setHatchSample] = useState(null)
  const [showLegendAssistant, setShowLegendAssistant] = useState(false)
  const [showDetection, setShowDetection] = useState(false)
  const [showReview, setShowReview] = useState(false)
  const [showRegionEditor, setShowRegionEditor] = useState(false)
  const [showSectionPanel, setShowSectionPanel] = useState(false)
  const [rawDetections, setRawDetections] = useState([])
  const [acceptedDetections, setAcceptedDetections] = useState([])
  const [reviewSummary, setReviewSummary] = useState(null)
  const [corrections, setCorrections] = useState([])
  const [heightMeters, setHeightMeters] = useState('')
  const [heightConfirmed, setHeightConfirmed] = useState(false)
  const [planNotes, setPlanNotes] = useState('Ready for manual legend and hatch selection.')
  const [componentName, setComponentName] = useState(COMPONENT_NAME)
  const [activeStep, setActiveStep] = useState(0)

  const renderedPageUrl = page_image_url.startsWith('http') ? page_image_url : `${backendBase}${page_image_url}`

  const canConfirmHatchSample = Boolean(
    hatchBox &&
    hatchBox.w >= MIN_SAMPLE_SIZE &&
    hatchBox.h >= MIN_SAMPLE_SIZE &&
    String(componentName || '').trim().length > 0
  )
  const canAutoDetect = Boolean(scale && hatchSample?.hatch_sample_id)

  const hatchPreviewUrl = useMemo(() => {
    if (!hatchBox || !naturalSize.width || !naturalSize.height) return null
    const srcX = Math.max(0, Math.round((hatchBox.x / naturalSize.width) * 100))
    const srcY = Math.max(0, Math.round((hatchBox.y / naturalSize.height) * 100))
    const srcW = Math.max(1, Math.round((hatchBox.w / naturalSize.width) * 100))
    const srcH = Math.max(1, Math.round((hatchBox.h / naturalSize.height) * 100))
    return `${renderedPageUrl}#xywh=${srcX},${srcY},${srcW},${srcH}`
  }, [hatchBox, naturalSize, renderedPageUrl])

  const acceptedDetectionAreaPx = useMemo(
    () => acceptedDetections.reduce((sum, region) => sum + areaFromRect(region), 0),
    [acceptedDetections]
  )
  const addedCorrectionAreaPx = useMemo(
    () => corrections.filter((item) => item.kind === 'add').reduce((sum, region) => sum + areaFromRect(region), 0),
    [corrections]
  )
  const subtractedCorrectionAreaPx = useMemo(
    () =>
      corrections
        .filter((item) => item.kind === 'subtract')
        .reduce((sum, region) => sum + areaFromRect(region) * correctionCount(region), 0),
    [corrections]
  )
  const pxPerSquareMeter = scale ? scale.pixelsPerMeter ** 2 : null
  const acceptedDetectionArea = pxPerSquareMeter ? acceptedDetectionAreaPx / pxPerSquareMeter : 0
  const addedCorrectionArea = pxPerSquareMeter ? addedCorrectionAreaPx / pxPerSquareMeter : 0
  const subtractedCorrectionArea = pxPerSquareMeter ? subtractedCorrectionAreaPx / pxPerSquareMeter : 0

  const deductions = useMemo(
    () =>
      corrections
        .filter((item) => item.kind === 'subtract' && (item.deduction_type === 'window' || item.deduction_type === 'door'))
        .map((item) => ({
          type: item.deduction_type,
          count: correctionCount(item),
          unit_area_m2: Number(item.area_m2 || 0),
          line_total_m2: correctionLineTotalM2(item),
        })),
    [corrections]
  )

  const quantity = buildQuantityResult({
    acceptedDetectionAreaM2: acceptedDetectionArea,
    addedCorrectionAreaM2: addedCorrectionArea,
    subtractedCorrectionAreaM2: subtractedCorrectionArea,
    confirmedHeightM: Number(heightMeters || 0),
  })

  const detectionReviewReady = showReview || Boolean(reviewSummary)

  const stepDefs = [
    { label: 'Upload & Scale', unlocked: true },
    { label: 'Select Component', unlocked: Boolean(scale) },
    { label: 'Review Quantity', unlocked: detectionReviewReady },
    { label: 'Export', unlocked: heightConfirmed && quantity.volume_m3 > 0 },
  ]

  const goToStep = (index) => {
    if (!stepDefs[index]?.unlocked) return
    setActiveStep(index)
  }

  const setSelectionModeSafe = (mode) => {
    selectionModeRef.current = mode
    setSelectionMode(mode)
  }

  const buildCorrection = (kind, rect) => {
    if (!rect) return null
    const area_pixels = areaFromRect(rect)
    const area_m2 = scale?.pixelsPerMeter ? area_pixels / (scale.pixelsPerMeter ** 2) : 0
    return {
      id: `${kind}-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
      kind,
      x: rect.x,
      y: rect.y,
      w: rect.w,
      h: rect.h,
      bbox: { x: rect.x, y: rect.y, width: rect.w, height: rect.h },
      area_pixels,
      area_m2,
      deduction_type: null,
      count: 1,
    }
  }

  const updateCorrectionDeduction = (id, patch) => {
    setCorrections((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)))
  }

  const handleImageLoad = (event) => {
    const img = event.currentTarget
    setNaturalSize({ width: img.naturalWidth, height: img.naturalHeight })
    setViewSize({ width: img.clientWidth, height: img.clientHeight })
  }

  const getPoint = (event) => {
    if (!containerRef.current) return null
    const rect = containerRef.current.getBoundingClientRect()
    const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left))
    const y = Math.max(0, Math.min(rect.height, event.clientY - rect.top))
    return { x, y }
  }

  const beginSelection = (event) => {
    const mode = selectionModeRef.current
    if (!mode) return
    const point = getPoint(event)
    if (!point) return
    if (mode === 'hatch_click') {
      if (!naturalSize.width || !naturalSize.height || !viewSize.width || !viewSize.height) return
      const scaleX = naturalSize.width / viewSize.width
      const scaleY = naturalSize.height / viewSize.height
      const centerX = point.x * scaleX
      const centerY = point.y * scaleY
      const nextHatch = clampBoxToImage(
        {
          x: centerX - CLICK_SAMPLE_SIZE / 2,
          y: centerY - CLICK_SAMPLE_SIZE / 2,
          w: CLICK_SAMPLE_SIZE,
          h: CLICK_SAMPLE_SIZE,
        },
        naturalSize
      )
      setHatchBox(nextHatch)
      setHatchSample(null)
      setPlanNotes('Hatch sample created from click fallback. Adjust if needed and confirm.')
      return
    }
    if (mode === 'correction_add' || mode === 'correction_subtract') {
      if (!naturalSize.width || !naturalSize.height || !viewSize.width || !viewSize.height) return
      const scaleX = naturalSize.width / viewSize.width
      const scaleY = naturalSize.height / viewSize.height
      const centerX = point.x * scaleX
      const centerY = point.y * scaleY
      const nextCorrection = clampBoxToImage(
        {
          x: centerX - CLICK_CORRECTION_SIZE / 2,
          y: centerY - CLICK_CORRECTION_SIZE / 2,
          w: CLICK_CORRECTION_SIZE,
          h: CLICK_CORRECTION_SIZE,
        },
        naturalSize
      )
      const kind = mode === 'correction_add' ? 'add' : 'subtract'
      const correction = buildCorrection(kind, nextCorrection)
      if (!correction) return
      setCorrections((prev) => [...prev, correction])
      setPlanNotes(kind === 'add' ? 'Added correction area.' : 'Added subtraction correction area.')
      selectionModeRef.current = null
      setSelectionMode(null)
      return
    }
    const nextDraft = { startX: point.x, startY: point.y, endX: point.x, endY: point.y }
    draftRectRef.current = nextDraft
    setDraftRect(nextDraft)
  }

  const moveSelection = (event) => {
    if (!draftRectRef.current) return
    const point = getPoint(event)
    if (!point) return
    const nextDraft = { ...draftRectRef.current, endX: point.x, endY: point.y }
    draftRectRef.current = nextDraft
    setDraftRect(nextDraft)
  }

  const endSelection = () => {
    const activeMode = selectionModeRef.current
    if (!draftRectRef.current || !activeMode) return
    const rect = toRectFromDraft(draftRectRef.current, naturalSize, viewSize)
    draftRectRef.current = null
    setDraftRect(null)
    if (!rect) return
    if (activeMode === 'legend') {
      setLegendBox(rect)
      setPlanNotes('Legend area captured. Select the hatch sample next.')
    } else if (activeMode === 'hatch') {
      setHatchBox(rect)
      setHatchSample(null)
      setPlanNotes('Hatch sample selected. Confirm it in the legend assistant.')
    } else if (activeMode === 'correction_add' || activeMode === 'correction_subtract') {
      const kind = activeMode === 'correction_add' ? 'add' : 'subtract'
      const correction = buildCorrection(kind, rect)
      if (!correction) return
      setCorrections((prev) => [...prev, correction])
      setPlanNotes(kind === 'add' ? 'Added correction area.' : 'Added subtraction correction area.')
    }
    selectionModeRef.current = null
    setSelectionMode(null)
  }

  const adjustHatchBox = (action) => {
    if (!hatchBox || !naturalSize.width || !naturalSize.height) return
    const sizeStep = 6
    let next = { ...hatchBox }
    if (action === 'smaller') {
      next.w = Math.max(MIN_SAMPLE_SIZE, next.w - sizeStep)
      next.h = Math.max(MIN_SAMPLE_SIZE, next.h - sizeStep)
    } else if (action === 'larger') {
      next.w = next.w + sizeStep
      next.h = next.h + sizeStep
    } else if (action === 'left') {
      next.x = next.x - MOVE_STEP
    } else if (action === 'right') {
      next.x = next.x + MOVE_STEP
    } else if (action === 'up') {
      next.y = next.y - MOVE_STEP
    } else if (action === 'down') {
      next.y = next.y + MOVE_STEP
    }
    const clamped = clampBoxToImage(next, naturalSize)
    setHatchBox(clamped)
    setHatchSample(null)
  }

  const overlays = [
    ...acceptedDetections.map((item) => ({ ...item, overlayKind: 'accepted' })),
    ...corrections.map((item) => ({ ...item, overlayKind: item.kind })),
    ...(legendBox ? [{ ...legendBox, id: 'legend-box', overlayKind: 'legend' }] : []),
    ...(hatchBox ? [{ ...hatchBox, id: 'hatch-box', overlayKind: 'hatch' }] : []),
  ]

  const draftDisplayRect = draftRect
    ? {
        left: Math.min(draftRect.startX, draftRect.endX),
        top: Math.min(draftRect.startY, draftRect.endY),
        width: Math.abs(draftRect.endX - draftRect.startX),
        height: Math.abs(draftRect.endY - draftRect.startY),
      }
    : null

  return (
    <div className="card panel">
      <div className="field">
        <label>Project Name</label>
        <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
      </div>

      <div className="workflow-grid" style={{ marginBottom: 20 }}>
        {stepDefs.map((step, index) => {
          const isActive = activeStep === index
          const isDone = index < activeStep || (index === activeStep && stepDefs[index + 1]?.unlocked)
          return (
            <button
              key={step.label}
              type="button"
              className="workflow-step"
              disabled={!step.unlocked}
              aria-current={isActive ? 'step' : undefined}
              onClick={() => goToStep(index)}
              style={{
                textAlign: 'left',
                cursor: step.unlocked ? 'pointer' : 'not-allowed',
                borderColor: isActive ? 'var(--color-accent)' : undefined,
              }}
            >
              <strong>{index + 1}. {step.label}</strong>
              <div className={`status-pill ${isDone ? 'status-completed' : ''}`}>
                {isDone ? 'Completed' : isActive ? 'Active' : step.unlocked ? 'Ready' : 'Locked'}
              </div>
            </button>
          )
        })}
      </div>

      <div className="two-col">
        <div className="card panel">
          <strong>Recovered Plan Workspace</strong>
          <p className="muted" style={{ marginBottom: 12 }}>
            File ID: {file_id} | Source URL: {renderedPageUrl}
          </p>
          <p className="muted">
            {selectionMode ? `Selection mode: ${selectionMode}.` : planNotes}
          </p>
          <div
            className="plan-stage"
            onMouseDown={beginSelection}
            onMouseMove={moveSelection}
            onMouseUp={endSelection}
            onMouseLeave={endSelection}
            ref={containerRef}
          >
            <img alt="Uploaded floor plan preview" className="plan-image" src={renderedPageUrl} onLoad={handleImageLoad} />
            {overlays.map((rect) => {
              const display = toDisplayRect(rect, naturalSize, viewSize)
              if (!display) return null
              return (
                <div
                  key={rect.id}
                  className={`plan-overlay overlay-${rect.overlayKind}`}
                  style={{ left: display.left, top: display.top, width: display.width, height: display.height }}
                />
              )
            })}
            {draftDisplayRect && (
              <div className="plan-overlay overlay-draft" style={{ left: draftDisplayRect.left, top: draftDisplayRect.top, width: draftDisplayRect.width, height: draftDisplayRect.height }} />
            )}
          </div>
        </div>

        <div>
          {activeStep === 0 && (
            <div className="card panel" style={{ marginBottom: 16 }}>
              <h3>Confirm Plan Scale</h3>
              <div className="field">
                <label>Measured pixel distance</label>
                <input type="number" value={pixelDistance} onChange={(event) => setPixelDistance(event.target.value)} />
              </div>
              <div className="field">
                <label>Real distance (m)</label>
                <input type="number" value={realDistance} onChange={(event) => setRealDistance(event.target.value)} />
              </div>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <button className="btn" onClick={() => setScale({ pixelsPerMeter: Number(pixelDistance) / Number(realDistance || 1) })}>Confirm Plan Scale</button>
                <button className="btn btn-secondary" onClick={() => setScale(null)}>Reset Scale</button>
              </div>
              <p className="muted">Scale status: <strong>{scale ? 'Confirmed' : 'Not confirmed'}</strong></p>
              {scale && <p className="muted">Confirmed scale value: {round(scale.pixelsPerMeter, 2)} px/m</p>}
              <button className="btn" style={{ marginTop: 12 }} disabled={!scale} onClick={() => setActiveStep(1)}>
                Continue to Select Component
              </button>
            </div>
          )}

          {activeStep === 1 && (
            <div className="card panel">
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <button className="btn" disabled={!scale} onClick={() => setShowLegendAssistant((value) => !value)}>
                  {showLegendAssistant ? 'Hide Legend Assistant' : 'Open Legend Assistant'}
                </button>
                <button className="btn btn-secondary" disabled={!canAutoDetect} onClick={() => setShowDetection((value) => !value)}>
                  {showDetection ? 'Hide Detection' : 'Open Detection'}
                </button>
              </div>
              {scale && !canAutoDetect && (
                <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
                  Confirm a hatch sample in Legend Assistant to enable detection.
                </p>
              )}
              {canAutoDetect && rawDetections.length === 0 && (
                <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
                  Run detection to enable review.
                </p>
              )}
              {showLegendAssistant && (
                <div style={{ marginTop: 16 }}>
                  <LegendAssistantPanel
                    fileId={file_id}
                    componentName={componentName}
                    legendBox={legendBox}
                    hatchBox={hatchBox}
                    hatchSample={hatchSample}
                    hatchClickMode={selectionMode === 'hatch_click'}
                    canConfirmHatchSample={canConfirmHatchSample}
                    hatchPreviewUrl={hatchPreviewUrl}
                    debug={{
                      selectionMode: selectionMode || 'null',
                      legendBox: legendBox ? JSON.stringify(legendBox) : 'null',
                      hatchBox: hatchBox ? JSON.stringify(hatchBox) : 'null',
                      backendHatchSampleId: hatchSample?.hatch_sample_id || 'null',
                      canConfirmHatchSample,
                      canAutoDetect,
                    }}
                    vlmNotes="VLM can suggest context only. Final sample selection stays user-confirmed."
                    onStartLegendSelection={() => setSelectionModeSafe('legend')}
                    onStartHatchSelection={() => setSelectionModeSafe('hatch')}
                    onStartHatchClickSelection={() => setSelectionModeSafe('hatch_click')}
                    onAdjustHatchBox={adjustHatchBox}
                    onHatchSampleSaved={(sample) => {
                      setHatchSample(sample)
                      setPlanNotes('Backend Sample Saved')
                    }}
                    onClose={() => setShowLegendAssistant(false)}
                  />
                </div>
              )}
              {showDetection && (
                <div style={{ marginTop: 16 }}>
                  <HatchDetectionPanel
                    fileId={file_id}
                    componentName={componentName}
                    hatchSample={hatchSample}
                    scale={scale}
                    detectionCount={rawDetections.length}
                    onDetectionComplete={(detections) => {
                      setRawDetections(detections)
                      setAcceptedDetections(detections)
                      setReviewSummary(null)
                      setShowReview(true)
                    }}
                    onClose={() => setShowDetection(false)}
                  />
                </div>
              )}
              <button className="btn" style={{ marginTop: 16 }} disabled={!detectionReviewReady} onClick={() => setActiveStep(2)}>
                Continue to Review Quantity
              </button>
            </div>
          )}
        </div>
      </div>

      {activeStep === 2 && (
        <div className="card panel" style={{ marginTop: 16 }}>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button className="btn btn-secondary" disabled={rawDetections.length === 0} onClick={() => setShowReview((value) => !value)}>
              {showReview ? 'Hide Review' : 'Open Review'}
            </button>
          </div>
          {showReview && (
            <div style={{ marginTop: 16 }}>
              <DetectionReviewPanel detections={rawDetections} onConfirm={({ acceptedDetections, summary }) => {
                setAcceptedDetections(acceptedDetections)
                setReviewSummary({ ...summary, component: componentName })
                setShowReview(false)
              }} onClose={() => setShowReview(false)} />
            </div>
          )}
        </div>
      )}

      {activeStep === 2 && reviewSummary && (
        <div className="card panel" style={{ marginTop: 16 }}>
          <h3>Reviewed Detection Areas</h3>
          <p className="muted">Accepted detections: <strong>{reviewSummary.accepted}</strong> | Rejected: <strong>{reviewSummary.rejected}</strong> | Deleted: <strong>{reviewSummary.deleted}</strong></p>
          <p className="muted">Accepted backend area: <strong>{round(acceptedDetectionArea, 4)} m2</strong></p>
          <button className="btn btn-secondary" onClick={() => setShowRegionEditor((value) => !value)}>
            {showRegionEditor ? 'Hide Correction Tool' : 'Open Correction Tool'}
          </button>
          {showRegionEditor && (
            <div style={{ marginTop: 16 }}>
              <RegionEditor
                corrections={corrections}
                addedCorrectionAreaM2={round(addedCorrectionArea, 4)}
                subtractedCorrectionAreaM2={round(subtractedCorrectionArea, 4)}
                onStartAdd={() => setSelectionModeSafe('correction_add')}
                onStartSubtract={() => setSelectionModeSafe('correction_subtract')}
                onRemoveCorrection={(id) => setCorrections((prev) => prev.filter((item) => item.id !== id))}
                onTagDeduction={updateCorrectionDeduction}
                onClose={() => setShowRegionEditor(false)}
              />
            </div>
          )}
        </div>
      )}

      {activeStep === 2 && reviewSummary && (
        <div className="card panel" style={{ marginTop: 16 }}>
          <h3>Height Assistant</h3>
          <p className="muted">VLM/AI can suggest height context only. Final m3 stays blocked until user confirms height.</p>
          <div className="field">
            <label>Component Name</label>
            <input value={componentName} onChange={(event) => setComponentName(event.target.value)} />
          </div>
          <div className="field">
            <label>Confirmed height / thickness (m)</label>
            <input value={heightMeters} onChange={(event) => { setHeightMeters(event.target.value); setHeightConfirmed(false) }} type="number" step="0.001" />
          </div>
          <p className="muted">Height status: <strong>{heightConfirmed ? 'Confirmed' : 'Not confirmed'}</strong></p>
          <button className="btn" onClick={() => setShowSectionPanel((value) => !value)}>
            {showSectionPanel ? 'Hide Height Assistant' : 'Open Height Assistant'}
          </button>
          {showSectionPanel && (
            <div style={{ marginTop: 16 }}>
              <SectionHeightPanel onConfirmHeight={({ height_m }) => { setHeightMeters(height_m); setHeightConfirmed(true); setShowSectionPanel(false) }} onClose={() => setShowSectionPanel(false)} />
            </div>
          )}
        </div>
      )}

      {activeStep === 2 && heightConfirmed && quantity.final_area_m2 > 0 && (
        <div className="card panel" style={{ marginTop: 16 }}>
          <h3>Calculate Quantity</h3>
          <table style={{ width: '100%' }}>
            <tbody>
              <tr><td><strong>Component</strong></td><td>{componentName}</td></tr>
              <tr><td><strong>Accepted detections</strong></td><td>{reviewSummary?.accepted || 0}</td></tr>
              <tr><td><strong>Final area (m²)</strong></td><td>{round(quantity.final_area_m2, 4)}</td></tr>
              <tr><td><strong>Height (m)</strong></td><td>{round(heightMeters, 3)}</td></tr>
              <tr><td><strong>Volume (m³)</strong></td><td>{round(quantity.volume_m3, 4)}</td></tr>
            </tbody>
          </table>
          <details className="advanced-details" style={{ marginTop: 12 }}>
            <summary>Advanced details</summary>
            <p className="muted" style={{ marginTop: 8 }}>
              final_area_m2 = accepted_detection_area_m2 + added_correction_area_m2 - subtracted_correction_area_m2; volume_m3 = final_area_m2 x confirmed_height_m
            </p>
            <table style={{ width: '100%', marginTop: 8 }}>
              <tbody>
                <tr><td><strong>accepted_detection_area_m2</strong></td><td>{round(acceptedDetectionArea, 4)}</td></tr>
                <tr><td><strong>added_correction_area_m2</strong></td><td>{round(addedCorrectionArea, 4)}</td></tr>
                <tr><td><strong>subtracted_correction_area_m2</strong></td><td>{round(subtractedCorrectionArea, 4)}</td></tr>
                <tr><td><strong>final_area_m2</strong></td><td>{round(quantity.final_area_m2, 4)}</td></tr>
                <tr><td><strong>volume_m3</strong></td><td>{round(quantity.volume_m3, 4)}</td></tr>
              </tbody>
            </table>
          </details>
          <button className="btn" style={{ marginTop: 12 }} disabled={!(heightConfirmed && quantity.volume_m3 > 0)} onClick={() => setActiveStep(3)}>
            Continue to Export
          </button>
        </div>
      )}

      {activeStep === 3 && heightConfirmed && quantity.volume_m3 > 0 && (
        <div className="card panel" style={{ marginTop: 16 }}>
          <h3>Export</h3>
          <p className="muted">
            Final area {round(quantity.final_area_m2, 4)} m², height {round(heightMeters, 3)} m, volume {round(quantity.volume_m3, 4)} m³.
          </p>
          <ExportButton
            projectName={projectName}
            planName={file_id}
            componentName={componentName}
            areaM2={quantity.final_area_m2}
            acceptedDetectionAreaM2={acceptedDetectionArea}
            addedCorrectionAreaM2={addedCorrectionArea}
            subtractedCorrectionAreaM2={subtractedCorrectionArea}
            heightM={heightMeters}
            volumeM3={quantity.volume_m3}
            deductions={deductions}
            detectionMethod="Backend hatch detection with user review and correction polygons"
            reviewStatus="Completed"
            notes={`Legend sample confirmed for ${componentName}. Accepted ${reviewSummary?.accepted || 0} backend detection(s).`}
          />
        </div>
      )}
    </div>
  )
}
