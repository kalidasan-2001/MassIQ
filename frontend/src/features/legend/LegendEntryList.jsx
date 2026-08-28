import React from 'react'

const STATUS_LABELS = {
  draft: 'Draft',
  ocr_complete: 'OCR Complete',
  confirmed: 'Confirmed',
}

export default function LegendEntryList({ entries, activeEntryId, onSelect, onCreateNew, creating }) {
  return (
    <div className="card panel">
      <h3>Legend Entries</h3>
      <button type="button" className="btn" disabled={creating} onClick={onCreateNew} style={{ marginBottom: 12 }}>
        {creating ? 'Creating...' : '+ New Legend Entry'}
      </button>
      {entries.length === 0 && <p className="muted">No legend entries yet for this page.</p>}
      <div style={{ display: 'grid', gap: 8 }} data-testid="legend-entry-list">
        {entries.map((entry) => (
          <button
            type="button"
            key={entry.id}
            className="workflow-step"
            style={{
              textAlign: 'left',
              cursor: 'pointer',
              borderColor: entry.id === activeEntryId ? 'var(--color-accent)' : undefined,
            }}
            onClick={() => onSelect?.(entry.id)}
          >
            <strong>{entry.material_name || entry.corrected_text || entry.raw_ocr_text || '(no description yet)'}</strong>
            <div className={`status-pill ${entry.status === 'confirmed' ? 'status-completed' : ''}`}>
              {STATUS_LABELS[entry.status] || entry.status}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
