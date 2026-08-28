import React, { useState } from 'react'

const round = (value, decimals) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  const factor = 10 ** decimals
  return (Math.round(Number(value) * factor) / factor).toFixed(decimals)
}

/**
 * R7: drawing-scale confirmation, confirmed dimension, and the
 * authoritative backend-computed QuantityResult (area/volume) for one
 * DetectionRun. Deliberately three concerns in one panel (scale,
 * dimension, result) since they form one linear "confirm scale -> confirm
 * dimension -> calculate" sequence the user works through in order --
 * splitting further would just scatter one workflow across more files
 * with no reuse benefit (R7 section 25: "functional first").
 *
 * Never derives the confirmed dimension automatically (R7 section 17) --
 * `suggestedThicknessMm` (from LegendEntry.thickness_mm) is offered only
 * as a one-click convenience, exactly like LegendEntryEditor's own
 * thickness suggestion button.
 */
export default function QuantityPanel({
  scale,
  quantity,
  suggestedThicknessMm,
  busy,
  disabled,
  reviewCounts,
  onConfirmDeclaredScale,
  onConfirmCalibratedScale,
  onCalculate,
  onConfirmResult,
}) {
  const [scaleMethod, setScaleMethod] = useState('declared_scale')
  const [declaredRatio, setDeclaredRatio] = useState('100')
  const [calibratedPlanPoints, setCalibratedPlanPoints] = useState('')
  const [calibratedRealM, setCalibratedRealM] = useState('')
  const [dimensionM, setDimensionM] = useState('')

  const handleConfirmScale = () => {
    if (scaleMethod === 'declared_scale') {
      onConfirmDeclaredScale?.(Number(declaredRatio))
    } else {
      onConfirmCalibratedScale?.(Number(calibratedPlanPoints), Number(calibratedRealM))
    }
  }

  const handleCalculate = () => {
    onCalculate?.(Number(dimensionM))
  }

  const suggestedDimensionM = suggestedThicknessMm != null ? suggestedThicknessMm / 1000 : null

  return (
    <div>
      <h3>Quantity</h3>

      <p className="muted" style={{ marginBottom: 4 }} data-testid="review-counts">
        Candidates {reviewCounts.candidate}, Accepted {reviewCounts.accepted}, Rejected {reviewCounts.rejected},
        Manual additions {reviewCounts.manualAdd}, Manual subtractions {reviewCounts.manualSubtract}.
      </p>

      <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #e2e8ef' }}>
        <p className="muted" style={{ marginBottom: 6 }}>Drawing scale</p>
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

      <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #e2e8ef' }}>
        <div className="field">
          <label htmlFor="confirmed-dimension">Confirmed height / thickness (m)</label>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              id="confirmed-dimension"
              type="number"
              value={dimensionM}
              onChange={(event) => setDimensionM(event.target.value)}
              style={{ width: 140 }}
              data-testid="confirmed-dimension-input"
            />
            {suggestedDimensionM != null && Number(dimensionM) !== suggestedDimensionM && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setDimensionM(String(suggestedDimensionM))}
              >
                Use suggested {suggestedDimensionM} m
              </button>
            )}
          </div>
        </div>
        <button
          type="button"
          className="btn"
          disabled={busy || disabled || !scale}
          onClick={handleCalculate}
          data-testid="calculate-quantity-btn"
        >
          Calculate Quantity
        </button>
        {!scale && (
          <p className="muted" style={{ marginTop: 6, fontSize: 13 }}>Confirm the drawing scale before calculating.</p>
        )}
      </div>

      {quantity && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #e2e8ef' }} data-testid="quantity-result">
          <div
            className={`status-pill ${quantity.status === 'confirmed' ? 'status-completed' : ''}`}
            data-testid="quantity-status"
          >
            {quantity.status === 'confirmed' ? 'Confirmed' : 'Draft'}
          </div>
          <table style={{ marginTop: 8 }}>
            <tbody>
              <tr>
                <td>Area</td>
                <td data-testid="quantity-area">{round(quantity.final_area_m2, 2)} m&sup2;</td>
              </tr>
              <tr>
                <td>Dimension</td>
                <td data-testid="quantity-dimension">{round(quantity.confirmed_dimension_m, 3)} m</td>
              </tr>
              <tr>
                <td>Volume</td>
                <td data-testid="quantity-volume">{round(quantity.volume_m3, 3)} m&sup3;</td>
              </tr>
            </tbody>
          </table>
          {quantity.status !== 'confirmed' && (
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={onConfirmResult}
              style={{ marginTop: 8 }}
              data-testid="confirm-quantity-btn"
            >
              Confirm Result
            </button>
          )}
        </div>
      )}
    </div>
  )
}
