import React from 'react'

/**
 * R9 Review stage: the accept/reject half of what used to be
 * DetectionPanel.jsx (R6). Split from the run-detection control
 * (DetectionRunPanel.jsx) so Review is its own workflow stage. All
 * existing data-testids preserved -- accepting/rejecting a region here
 * only changes its own persisted review status; nothing here computes or
 * writes area/volume.
 */
export default function RegionReviewList({ regions, busy, onUpdateRegionStatus }) {
  if (!regions || regions.length === 0) {
    return <p className="muted">Run analysis first to see candidate regions here.</p>
  }

  return (
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
  )
}
