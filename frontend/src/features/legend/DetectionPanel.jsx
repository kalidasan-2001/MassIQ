import React from 'react'

/**
 * R6: minimal Detection Engine V2 UI -- "Run Detection V2" using the
 * active (confirmed, featured) LegendEntry as the reference pattern, a
 * status pill, and a list of candidate regions with accept/reject
 * actions. Deliberately functional, not polished -- reuses existing btn/
 * status-pill classes, same discipline as R5's PatternMatchesPanel.
 *
 * Detection produces CANDIDATE regions only (R6 section 1/23): accepting
 * a region here only changes its own persisted review status. Nothing
 * here computes or writes area/volume -- that remains the existing,
 * untouched frontend quantityEngine's job over whatever state a human
 * explicitly accepted.
 */
export default function DetectionPanel({ run, regions, busy, disabled, onRunDetection, onUpdateRegionStatus }) {
  return (
    <div>
      <h3>Detection Engine V2</h3>
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

      {regions && regions.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, marginTop: 10 }} data-testid="detected-region-list">
          {regions.map((region, index) => (
            <li
              key={region.id}
              style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', flexWrap: 'wrap' }}
              data-testid="detected-region"
            >
              <span className="muted" style={{ fontSize: 13 }}>
                Region {index + 1} -- similarity {(region.similarity * 100).toFixed(0)}%
              </span>
              {region.status === 'candidate' ? (
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    type="button"
                    className="btn"
                    disabled={busy}
                    onClick={() => onUpdateRegionStatus(region.id, 'accepted')}
                    data-testid="accept-region-btn"
                  >
                    Accept
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={busy}
                    onClick={() => onUpdateRegionStatus(region.id, 'rejected')}
                    data-testid="reject-region-btn"
                  >
                    Reject
                  </button>
                </div>
              ) : (
                <span className="status-pill status-completed">{region.status}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
