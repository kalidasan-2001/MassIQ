import React from 'react'

/**
 * R7: manual ADD/SUBTRACT geometry corrections layered on top of one
 * DetectionRun's review. Deliberately mirrors DetectionPanel.jsx's own
 * scope/shape (mode buttons + a list), reusing the same
 * usePageSelection.js drag mechanism the pattern/description selections
 * already use -- `mode` is just a string it doesn't hardcode, so
 * 'manual_add'/'manual_subtract' work with zero changes there.
 *
 * State visibility (R7 section 26): every correction shows an explicit
 * "Added"/"Subtracted" label, not just a color -- this also gives
 * Playwright something reliable to assert on.
 */
export default function ManualCorrectionPanel({
  mode,
  corrections,
  busy,
  disabled,
  onStartAdd,
  onStartSubtract,
  onCancel,
  onDeleteCorrection,
}) {
  const additions = corrections.filter((c) => c.correction_type === 'add')
  const subtractions = corrections.filter((c) => c.correction_type === 'subtract')

  return (
    <div>
      <h3>Manual Corrections</h3>
      <p className="muted" style={{ marginBottom: 6 }}>
        Draw geometry Detection V2 missed (Add), or remove geometry it wrongly included (Subtract).
      </p>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <button
          type="button"
          className="btn"
          disabled={disabled || busy}
          onClick={onStartAdd}
          data-testid="manual-add-btn"
        >
          {mode === 'manual_add' ? 'Drawing Add region...' : 'Manual Add'}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={disabled || busy}
          onClick={onStartSubtract}
          data-testid="manual-subtract-btn"
        >
          {mode === 'manual_subtract' ? 'Drawing Subtract region...' : 'Manual Subtract'}
        </button>
        {mode && (
          <button type="button" className="btn btn-ghost" onClick={onCancel} data-testid="manual-cancel-btn">
            Cancel
          </button>
        )}
      </div>

      <p className="muted" style={{ marginTop: 10, fontSize: 13 }} data-testid="manual-correction-counts">
        {additions.length} manual addition{additions.length === 1 ? '' : 's'}, {subtractions.length} manual
        subtraction{subtractions.length === 1 ? '' : 's'}.
      </p>

      {corrections.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, marginTop: 8 }} data-testid="manual-correction-list">
          {corrections.map((correction) => (
            <li
              key={correction.id}
              style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', flexWrap: 'wrap' }}
              data-testid="manual-correction-item"
            >
              <span
                className={`status-pill ${correction.correction_type === 'add' ? 'status-completed' : ''}`}
                data-testid="manual-correction-label"
              >
                {correction.correction_type === 'add' ? 'Added' : 'Subtracted'}
              </span>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={busy}
                onClick={() => onDeleteCorrection(correction.id)}
                data-testid="manual-correction-delete-btn"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
