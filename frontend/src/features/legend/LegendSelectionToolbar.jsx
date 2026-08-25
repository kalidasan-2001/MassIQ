import React from 'react'

/**
 * The two-selection toolbar the R3 product principle requires: the user
 * deliberately starts one mode at a time and draws a rectangle on the
 * plan. No automatic legend-layout detection, no AI-guessed pairing --
 * see docs/releases/R3_LEGEND_WORKFLOW_CHECKLIST.md's "two-selection
 * workflow" section for why this extra click is intentional.
 */
export default function LegendSelectionToolbar({ mode, disabled, onStartPattern, onStartDescription, onCancel }) {
  return (
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
      <button
        type="button"
        className="btn"
        disabled={disabled}
        aria-pressed={mode === 'pattern'}
        onClick={onStartPattern}
      >
        {mode === 'pattern' ? 'Drawing Pattern... (drag on plan)' : 'Select Pattern'}
      </button>
      <button
        type="button"
        className="btn btn-secondary"
        disabled={disabled}
        aria-pressed={mode === 'description'}
        onClick={onStartDescription}
      >
        {mode === 'description' ? 'Drawing Description... (drag on plan)' : 'Select Description'}
      </button>
      {mode && (
        <button type="button" className="btn btn-secondary" onClick={onCancel}>
          Cancel Selection
        </button>
      )}
    </div>
  )
}
