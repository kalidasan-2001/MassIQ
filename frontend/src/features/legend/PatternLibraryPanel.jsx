import React, { useEffect, useState } from 'react'
import * as legendApi from './api'

/**
 * R5: minimal project-level Pattern Library view (R5 section 30) --
 * pattern thumbnail, material, confirmations, created date. No filtering,
 * no bulk editing, no hierarchy UI -- those are explicitly out of scope.
 */
export default function PatternLibraryPanel({ projectId, refreshKey }) {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const refresh = () => {
    if (!projectId) return
    setLoading(true)
    setError('')
    legendApi
      .listPatternLibrary(projectId)
      .then(setEntries)
      .catch((err) => setError(err?.response?.data?.detail || err.message || 'Failed to load the pattern library.'))
      .finally(() => setLoading(false))
  }

  // Re-fetches whenever the caller bumps refreshKey (e.g. after adding a
  // LegendEntry to the library elsewhere on the page), not just on mount
  // -- this panel and the workspace that adds entries are siblings with
  // no other shared state.
  useEffect(refresh, [projectId, refreshKey])

  if (!projectId) return null

  return (
    <div className="card panel" style={{ marginTop: 16 }} data-testid="pattern-library-panel">
      <h3>Project Pattern Library</h3>
      <button type="button" className="btn btn-secondary" onClick={refresh} disabled={loading}>
        Refresh
      </button>
      {error && <p className="error">{error}</p>}
      {!loading && entries.length === 0 && <p className="muted">No confirmed patterns added to this project’s library yet.</p>}
      {entries.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, marginTop: 10 }} data-testid="library-entry-list">
          {entries.map((entry) => (
            <li
              key={entry.id}
              style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0' }}
              data-testid="library-entry"
            >
              <img
                src={legendApi.patternCropUrl(projectId, entry.source_plan_id, entry.source_legend_entry_id)}
                alt={`Pattern for ${entry.canonical_material_name}`}
                style={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 6, border: '1px solid #cbd7df' }}
                onError={(event) => {
                  event.currentTarget.style.visibility = 'hidden'
                }}
              />
              <div>
                <strong>{entry.canonical_material_name}</strong>
                {entry.material_code && <span className="muted"> ({entry.material_code})</span>}
                <div className="muted" style={{ fontSize: 13 }}>
                  Confirmed {entry.confirmation_count}x -- added {new Date(entry.created_at).toLocaleDateString()}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
