import React from 'react'

const DEDUCTION_LABELS = { window: 'Window', door: 'Door' }

const clampCount = (value) => Math.max(1, Math.round(Number(value) || 1))

export default function RegionEditor({
  corrections,
  addedCorrectionAreaM2,
  subtractedCorrectionAreaM2,
  onStartAdd,
  onStartSubtract,
  onRemoveCorrection,
  onTagDeduction,
  onClose,
}) {
  return (
    <div className="card panel">
      <h3>Correction Tool</h3>
      <p className="muted">
        Manual polygon correction is only a fallback after automatic detection review. Draw add or
        subtract rectangles on the plan only for missed or incorrect areas.
      </p>
      <p className="muted">Click on the plan to place an add/subtract correction area.</p>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
        <button className="btn" data-testid="add-correction-btn" onClick={onStartAdd}>
          Add Correction Area
        </button>
        <button className="btn btn-secondary" data-testid="subtract-correction-btn" onClick={onStartSubtract}>
          Subtract Correction Area
        </button>
        <button className="btn btn-secondary" onClick={onClose}>
          Close
        </button>
      </div>
      <p className="muted" data-testid="added-correction-total">
        Added correction total (m2): <strong>{addedCorrectionAreaM2}</strong>
      </p>
      <p className="muted" data-testid="subtracted-correction-total">
        Subtracted correction total (m2): <strong>{subtractedCorrectionAreaM2}</strong>
      </p>
      <div style={{ display: 'grid', gap: 8 }}>
        {corrections.length === 0 && <p className="muted">No correction polygons added.</p>}
        {corrections.map((region) => {
          const isSubtract = region.kind === 'subtract'
          const isTagged = isSubtract && (region.deduction_type === 'window' || region.deduction_type === 'door')
          const count = clampCount(region.count)
          const unitArea = Number(region.area_m2 || 0)
          const lineTotal = unitArea * count
          return (
            <div key={region.id} className="workflow-step">
              <div>
                <strong>{isTagged ? DEDUCTION_LABELS[region.deduction_type] : region.kind === 'add' ? 'Add' : 'Subtract'}</strong>
                {' '}| {region.w} x {region.h}px
                {isTagged ? (
                  <>{' '}| {unitArea.toFixed(4)} m2 x {count} = {lineTotal.toFixed(4)} m2</>
                ) : (
                  <>{' '}| {unitArea.toFixed(4)} m2</>
                )}
              </div>
              {isSubtract && (
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginTop: 8 }}>
                  <div className="field" style={{ marginBottom: 0 }}>
                    <label>Deduction type</label>
                    <select
                      value={region.deduction_type || ''}
                      onChange={(event) =>
                        onTagDeduction?.(region.id, { deduction_type: event.target.value || null })
                      }
                    >
                      <option value="">— (generic)</option>
                      <option value="window">Window</option>
                      <option value="door">Door</option>
                    </select>
                  </div>
                  {isTagged && (
                    <div className="field" style={{ marginBottom: 0 }}>
                      <label>Count</label>
                      <input
                        type="number"
                        min="1"
                        step="1"
                        value={count}
                        onChange={(event) => onTagDeduction?.(region.id, { count: clampCount(event.target.value) })}
                        style={{ width: 80 }}
                      />
                    </div>
                  )}
                </div>
              )}
              <button
                className="btn btn-secondary"
                onClick={() => onRemoveCorrection?.(region.id)}
                style={{ marginTop: 8 }}
              >
                Remove
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
