import React, { useState } from 'react'
import api from '../api/api'

export default function LegendAssistantPanel({
  fileId,
  componentName,
  legendBox,
  hatchBox,
  hatchSample,
  hatchClickMode,
  canConfirmHatchSample,
  hatchPreviewUrl,
  debug,
  vlmNotes,
  onStartLegendSelection,
  onStartHatchSelection,
  onStartHatchClickSelection,
  onAdjustHatchBox,
  onHatchSampleSaved,
  onClose,
}) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const nextActionHint = (() => {
    if (!canConfirmHatchSample) {
      if (!String(componentName || '').trim()) return 'Next: enter the component name.'
      return 'Next: select the hatch pattern from the legend.'
    }
    if (!hatchSample?.hatch_sample_id) return 'Next: confirm the hatch sample to save it.'
    if (!debug?.canAutoDetect) return 'Next: confirm the plan scale to enable detection.'
    return 'Ready: run detection from the Detection panel.'
  })()

  const saveHatchSample = async () => {
    if (!canConfirmHatchSample || !hatchBox) {
      setError('Select a hatch sample area on the plan before confirming.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const response = await api.post('/save-hatch-sample', {
        file_id: fileId,
        component_name: componentName,
        bbox: {
          x: hatchBox.x,
          y: hatchBox.y,
          width: hatchBox.w,
          height: hatchBox.h,
        },
      })
      onHatchSampleSaved?.(response.data)
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Could not save hatch sample.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card panel">
      <h3>Legend Assistant</h3>
      <p className="muted">
        Select the legend area for context, then drag a tight hatch sample for the active
        component. This sample is sent to the backend and used for real hatch detection.
      </p>
      {vlmNotes && <p className="muted">VLM note: {vlmNotes}</p>}
      <p className="muted"><strong>{nextActionHint}</strong></p>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <button className="btn" onClick={onStartLegendSelection}>
          Select Legend Area
        </button>
        <button className="btn btn-secondary" onClick={onStartHatchSelection}>
          Select Hatch Sample
        </button>
        <button className="btn btn-secondary" onClick={onStartHatchClickSelection}>
          {hatchClickMode ? 'Click Hatch Pattern: ON' : 'Click Hatch Pattern'}
        </button>
        <button className="btn" disabled={loading || !canConfirmHatchSample} onClick={saveHatchSample}>
          {loading ? 'Saving Hatch Sample...' : 'Confirm Hatch Sample'}
        </button>
        <button className="btn btn-secondary" onClick={onClose}>
          Close
        </button>
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 10 }}>
        <button className="btn btn-secondary" onClick={() => onAdjustHatchBox?.('smaller')}>Smaller</button>
        <button className="btn btn-secondary" onClick={() => onAdjustHatchBox?.('larger')}>Larger</button>
        <button className="btn btn-secondary" onClick={() => onAdjustHatchBox?.('left')}>Move Left</button>
        <button className="btn btn-secondary" onClick={() => onAdjustHatchBox?.('right')}>Move Right</button>
        <button className="btn btn-secondary" onClick={() => onAdjustHatchBox?.('up')}>Move Up</button>
        <button className="btn btn-secondary" onClick={() => onAdjustHatchBox?.('down')}>Move Down</button>
      </div>
      {hatchBox && <p className="muted">Hatch Sample: {hatchBox.w} x {hatchBox.h}px</p>}
      {hatchPreviewUrl && (
        <div style={{ marginTop: 10 }}>
          <p className="muted">Selected hatch preview</p>
          <img src={hatchPreviewUrl} alt="Hatch preview" style={{ width: 80, height: 80, objectFit: 'cover', borderRadius: 8, border: '1px solid #cbd7df' }} />
        </div>
      )}
      <details className="advanced-details" style={{ marginTop: 12 }}>
        <summary>Advanced details</summary>
        <div className="workflow-grid" style={{ marginTop: 12, marginBottom: 12 }}>
          <div className="workflow-step">
            <strong>Legend Area</strong>
            <div className={`status-pill ${legendBox ? 'status-completed' : 'status-progress'}`}>
              {legendBox ? `${legendBox.w} x ${legendBox.h}px` : 'Select on plan'}
            </div>
          </div>
          <div className="workflow-step">
            <strong>Hatch Sample</strong>
            <div className={`status-pill ${hatchBox ? 'status-completed' : 'status-progress'}`}>
              {hatchBox ? `${hatchBox.w} x ${hatchBox.h}px` : 'Select on plan'}
            </div>
          </div>
          <div className="workflow-step">
            <strong>Backend Sample</strong>
            <div className={`status-pill ${hatchSample ? 'status-completed' : 'status-progress'}`}>
              {hatchSample ? hatchSample.hatch_sample_id.slice(0, 8) : 'Not saved'}
            </div>
          </div>
        </div>
        {debug && (
          <pre className="debug-box">
{`selectionMode=${debug.selectionMode}
legendBox=${debug.legendBox}
hatchBox=${debug.hatchBox}
backendHatchSampleId=${debug.backendHatchSampleId}
canConfirmHatchSample=${debug.canConfirmHatchSample}
canAutoDetect=${debug.canAutoDetect}`}
          </pre>
        )}
      </details>
      {error && <p className="error">{error}</p>}
    </div>
  )
}
