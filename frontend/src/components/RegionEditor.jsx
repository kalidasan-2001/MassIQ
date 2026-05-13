import React from 'react'

export default function RegionEditor({
  corrections,
  addedCorrectionAreaM2,
  subtractedCorrectionAreaM2,
  onStartAdd,
  onStartSubtract,
  onRemoveCorrection,
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
        {corrections.map((region) => (
          <div key={region.id} className="workflow-step">
            <div>
              <strong>{region.kind === 'add' ? 'Add' : 'Subtract'}</strong> | {region.w} x {region.h}px
              {' '}| {Number(region.area_m2 || 0).toFixed(4)} m2
            </div>
            <button
              className="btn btn-secondary"
              onClick={() => onRemoveCorrection?.(region.id)}
              style={{ marginTop: 8 }}
            >
              Remove
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
