import React, { useEffect, useState } from 'react'
import * as legendApi from './api'

/**
 * R5: minimal "Possible matches" UI for one confirmed LegendEntry with
 * computed hatch features. Deliberately functional, not polished --
 * reuses existing btn/status-pill classes. Shows Top-K project-library
 * suggestions with an explicit SIMILARITY score (never "confidence" or
 * "probability" -- see R5 section 29) and lets the user accept, reject,
 * or ignore each one; nothing here is required to confirm a LegendEntry
 * (the library is optional assistance, see R5 section 39).
 */
export default function PatternMatchesPanel({ projectId, planId, legendEntryId, onUseMaterial }) {
  const [matches, setMatches] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [decidedIds, setDecidedIds] = useState({})

  // Restores previously-recorded decisions on load/reload (R5 section 37:
  // decisions must survive a browser reload) -- a decision with no
  // suggested_library_entry_id (a MANUAL entry never tied to a
  // suggestion) has nothing to restore a pill onto here.
  useEffect(() => {
    let cancelled = false
    setDecidedIds({})
    if (legendEntryId) {
      legendApi
        .listMatchDecisions(projectId, planId, legendEntryId)
        .then((decisions) => {
          if (cancelled) return
          const restored = {}
          for (const decision of decisions) {
            if (decision.suggested_library_entry_id && !(decision.suggested_library_entry_id in restored)) {
              restored[decision.suggested_library_entry_id] = decision.decision
            }
          }
          setDecidedIds(restored)
        })
        // Best-effort restore only -- a failed lookup (e.g. projectId/planId
        // not resolvable yet) must never surface as an uncaught rejection;
        // the "Find Matches" button still works from a clean state.
        .catch(() => {})
    }
    return () => {
      cancelled = true
    }
  }, [projectId, planId, legendEntryId])

  const handleFindMatches = async () => {
    setBusy(true)
    setError('')
    try {
      const result = await legendApi.computeMatches(projectId, planId, legendEntryId)
      setMatches(result)
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Failed to search the pattern library.')
    } finally {
      setBusy(false)
    }
  }

  const recordDecision = async (candidate, decision) => {
    setBusy(true)
    setError('')
    try {
      await legendApi.recordMatchDecision(projectId, planId, legendEntryId, {
        decision,
        suggested_library_entry_id: candidate.library_entry_id,
        similarity_at_decision: candidate.similarity,
        confirmed_material_name: decision === 'accepted' ? candidate.canonical_material_name : null,
      })
      setDecidedIds((prev) => ({ ...prev, [candidate.library_entry_id]: decision }))
      if (decision === 'accepted') {
        onUseMaterial?.(candidate)
      }
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Failed to record the decision.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid #e2e8ef' }}>
      <p className="muted" style={{ marginBottom: 6 }}>Possible matches (Project Pattern Library)</p>
      <button type="button" className="btn btn-secondary" disabled={busy} onClick={handleFindMatches}>
        Find Matches
      </button>

      {matches && matches.candidates.length === 0 && (
        <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
          {matches.reason === 'empty_library'
            ? 'No candidates yet -- add confirmed patterns to this project’s library first.'
            : matches.reason === 'no_comparable_candidates'
              ? 'No comparable candidates (feature version mismatch).'
              : 'No candidates.'}
        </p>
      )}

      {matches && matches.candidates.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, marginTop: 10 }} data-testid="match-candidate-list">
          {matches.candidates.map((candidate) => {
            const decided = decidedIds[candidate.library_entry_id]
            return (
              <li
                key={candidate.library_entry_id}
                style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', flexWrap: 'wrap' }}
                data-testid="match-candidate"
              >
                <img
                  src={legendApi.patternCropUrl(projectId, candidate.source_plan_id, candidate.source_legend_entry_id)}
                  alt={`Library pattern: ${candidate.canonical_material_name}`}
                  style={{ width: 48, height: 48, objectFit: 'cover', borderRadius: 6, border: '1px solid #cbd7df' }}
                />
                <div>
                  <strong>{candidate.canonical_material_name}</strong>
                  <div className="muted" style={{ fontSize: 13 }}>
                    {/* Explicitly "pattern similarity" -- never probability/confidence (R5 section 29). */}
                    Pattern similarity: {(candidate.similarity * 100).toFixed(0)}% ({candidate.similarity_band})
                  </div>
                </div>
                {decided ? (
                  <span className="status-pill status-completed">{decided}</span>
                ) : (
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      type="button"
                      className="btn"
                      disabled={busy}
                      onClick={() => recordDecision(candidate, 'accepted')}
                      data-testid="use-match-btn"
                    >
                      Use this
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={busy}
                      onClick={() => recordDecision(candidate, 'rejected')}
                      data-testid="reject-match-btn"
                    >
                      Reject
                    </button>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  )
}
