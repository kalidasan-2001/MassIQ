import React, { useState } from 'react'

const round = (value, decimals) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  const factor = 10 ** decimals
  return (Math.round(Number(value) * factor) / factor).toFixed(decimals)
}

/**
 * R9 Review stage: the dimension/quantity half of what used to be
 * QuantityPanel.jsx (R7) -- the scale-confirmation half moved to
 * ScaleConfirmationPanel.jsx (Plan Preparation stage). Deliberately
 * still requires a confirmed scale (passed in as `scale`, read-only here)
 * before calculation is enabled -- R7's authority rules are unchanged,
 * only where the scale form itself lives moved. All existing
 * data-testids preserved.
 */
export default function QuantityPanel({
  scale,
  quantity,
  suggestedThicknessMm,
  busy,
  disabled,
  reviewCounts,
  onCalculate,
  onConfirmResult,
}) {
  const [dimensionM, setDimensionM] = useState('')

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
