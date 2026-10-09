import React from 'react'

/**
 * R9 Analysis stage: the "run detection" half of what used to be
 * DetectionPanel.jsx (R6). Split from the candidate review list
 * (RegionReviewList.jsx) so Analysis (run + status) and Review
 * (accept/reject) can be presented as distinct workflow stages without
 * changing any detection behavior. All existing data-testids preserved.
 */
export default function DetectionRunPanel({ run, busy, disabled, onRunDetection }) {
  return (
    <div>
      <h3>Analyze the plan</h3>
      <p className="muted" style={{ marginBottom: 6 }}>Scans the whole page for regions resembling the selected reference pattern.</p>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        {run && (
          <div className={`status-pill ${run.status === 'completed' ? 'status-completed' : ''}`}>{run.status}</div>
        )}
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy || disabled}
          onClick={onRunDetection}
          data-testid="run-detection-btn"
        >
          {busy ? 'Scanning...' : 'Run Detection V2'}
        </button>
      </div>

      {run?.status === 'failed' && <p className="error">{run.error_message || 'Detection failed.'}</p>}

      {run?.status === 'completed' && (
        <p className="muted" style={{ marginTop: 6, fontSize: 13 }}>
          {run.tiles_evaluated} tiles evaluated, {run.tiles_skipped} skipped (low evidence), {run.candidate_region_count}{' '}
          candidate region{run.candidate_region_count === 1 ? '' : 's'} found.
        </p>
      )}
    </div>
  )
}
