import React, { useState } from 'react'

export default function SectionHeightPanel({ onConfirmHeight, onClose }) {
  const [height, setHeight] = useState('0.30')

  return (
    <div className="card panel">
      <div className="field">
        <label>Assistant suggested height (m)</label>
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
