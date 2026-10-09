import React, { useState } from 'react'

/**
 * R9 Plan Preparation stage: the drawing-scale half of what used to be
 * QuantityPanel.jsx (R7). Split out so scale confirmation is reachable
 * right after a plan page is selected, not gated behind a completed
 * Detection run -- that gate was an accident of layout, not a backend
 * dependency (PUT .../scale has no DetectionRun dependency). All existing
 * data-testids preserved.
 */
export default function ScaleConfirmationPanel({ scale, busy, disabled, onConfirmDeclaredScale, onConfirmCalibratedScale }) {
  const [scaleMethod, setScaleMethod] = useState('declared_scale')
  const [declaredRatio, setDeclaredRatio] = useState('100')
  const [calibratedPlanPoints, setCalibratedPlanPoints] = useState('')
  const [calibratedRealM, setCalibratedRealM] = useState('')

  const handleConfirmScale = () => {
    if (scaleMethod === 'declared_scale') {
      onConfirmDeclaredScale?.(Number(declaredRatio))
    } else {
      onConfirmCalibratedScale?.(Number(calibratedPlanPoints), Number(calibratedRealM))
    }
  }

  return (
    <div>
      <h3>Plan Preparation</h3>
      <p className="muted" style={{ marginBottom: 6 }}>Confirm the drawing scale for this page before analysis.</p>

      {scale ? (
        <p className="status-pill status-completed" data-testid="scale-status">
          Confirmed ({scale.method === 'declared_scale' ? `1:${scale.declared_ratio}` : 'calibrated distance'})
        </p>
      ) : (
        <p className="status-pill" data-testid="scale-status">Not confirmed</p>
      )}

      <div className="field">
        <label htmlFor="scale-method">Method</label>
        <select
          id="scale-method"
          className="select"
          value={scaleMethod}
          onChange={(event) => setScaleMethod(event.target.value)}
          data-testid="scale-method-select"
        >
          <option value="declared_scale">Declared scale (e.g. 1:100)</option>
          <option value="calibrated_distance">Calibrated distance</option>
        </select>
      </div>

      {scaleMethod === 'declared_scale' ? (
        <div className="field">
          <label htmlFor="declared-ratio">Ratio (the N in 1:N)</label>
          <input
            id="declared-ratio"
            type="number"
            value={declaredRatio}
            onChange={(event) => setDeclaredRatio(event.target.value)}
            data-testid="declared-ratio-input"
          />
        </div>
      ) : (
        <>
          <div className="field">
            <label htmlFor="calibrated-plan-points">Measured plan distance (points)</label>
            <input
              id="calibrated-plan-points"
              type="number"
              value={calibratedPlanPoints}
              onChange={(event) => setCalibratedPlanPoints(event.target.value)}
              data-testid="calibrated-plan-points-input"
            />
          </div>
          <div className="field">
            <label htmlFor="calibrated-real-m">Real-world distance (m)</label>
            <input
              id="calibrated-real-m"
              type="number"
              value={calibratedRealM}
              onChange={(event) => setCalibratedRealM(event.target.value)}
              data-testid="calibrated-real-m-input"
            />
          </div>
        </>
      )}
      <button
        type="button"
        className="btn btn-secondary"
        disabled={busy || disabled}
        onClick={handleConfirmScale}
        data-testid="confirm-scale-btn"
      >
        Confirm Scale
      </button>
    </div>
  )
}
