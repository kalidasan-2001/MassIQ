import React, { useMemo, useState } from 'react'

export default function DetectionReviewPanel({ detections, onConfirm, onClose }) {
  const [statuses, setStatuses] = useState(
    Object.fromEntries(detections.map((detection) => [detection.id, detection.status || 'accepted']))
  )

  const summary = useMemo(() => {
    const values = Object.values(statuses)
    return {
      total: values.length,
      accepted: values.filter((value) => value === 'accepted').length,
      rejected: values.filter((value) => value === 'rejected').length,
      deleted: values.filter((value) => value === 'deleted').length,
    }
  }, [statuses])

  const acceptedDetections = detections
    .map((detection) => ({ ...detection, status: statuses[detection.id] }))
    .filter((detection) => detection.status === 'accepted')

  return (
    <div className="card panel">
      <h3>Review Detected Component Areas</h3>
      <p className="muted">MassIQ detects first. The user only reviews and removes mistakes.</p>
      <div style={{ display: 'grid', gap: 8 }}>
        {detections.map((detection) => (
          <div key={detection.id} className="workflow-step">
            <div>
              <strong>{detection.id}</strong> | confidence {detection.confidence}
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              {['accepted', 'rejected', 'deleted'].map((status) => (
                <button
                  key={status}
                  className={`btn ${statuses[detection.id] === status ? '' : 'btn-secondary'}`}
                  onClick={() => setStatuses((prev) => ({ ...prev, [detection.id]: status }))}
                >
                  {status}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      <p className="muted" style={{ marginTop: 12 }}>
        Accepted: {summary.accepted} | Rejected: {summary.rejected} | Deleted: {summary.deleted}
      </p>
      <button
        className="btn"
        onClick={() => onConfirm?.({ acceptedDetections, summary })}
      >
        Confirm Review
      </button>
      <button className="btn btn-secondary" onClick={onClose} style={{ marginLeft: 10 }}>
        Close
      </button>
    </div>
  )
}
