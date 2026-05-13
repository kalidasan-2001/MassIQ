import React, { useState } from 'react'

export default function SectionHeightPanel({ onConfirmHeight, onClose }) {
  const [height, setHeight] = useState('0.30')

  return (
    <div className="card panel">
      <h3>Height Assistant</h3>
      <p className="muted">
        Confirm the final height or thickness in meters. Automatic section reading can be added
        later without changing the business workflow.
      </p>
      <div className="field">
        <label>Confirmed height / thickness (m)</label>
        <input value={height} onChange={(event) => setHeight(event.target.value)} type="number" step="0.001" />
      </div>
      <button
        className="btn"
        onClick={() => onConfirmHeight?.({ height_m: height, section_file_id: 'manual-section' })}
      >
        Confirm Height
      </button>
      <button className="btn btn-secondary" onClick={onClose} style={{ marginLeft: 10 }}>
        Close
      </button>
    </div>
  )
}
