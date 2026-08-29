import React from 'react'

const STATUS_LABELS = {
  uploaded: 'Uploaded',
  inspecting: 'Inspecting',
  ready: 'Ready',
  failed: 'Failed',
}

/**
 * R9 Plans stage: upload another plan, see every uploaded plan's
 * processing state, and pick which plan/page to work on. Lifted from
 * LegendFeaturePage.jsx's old always-visible "2. Plan" / "3. Page"
 * blocks -- same API calls, now presented as its own stage instead of a
 * permanently-visible grid cell.
 */
export default function PlansStage({ plans, planId, setPlanId, planFile, setPlanFile, onUploadPlan, loading, planDetail, pageNumber, setPageNumber, workflow }) {
  return (
    <div className="card panel">
      <h3>Plans</h3>
      {plans.length === 0 && (
        <p className="muted" data-testid="plans-empty">Upload your first construction plan.</p>
      )}

      {plans.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0 }} data-testid="plan-list">
          {plans.map((plan) => (
            <li key={plan.id} style={{ marginBottom: 6 }}>
              <button
                type="button"
                className="workflow-step"
                style={{ textAlign: 'left', width: '100%', cursor: 'pointer', borderColor: plan.id === planId ? 'var(--color-accent)' : undefined }}
                onClick={() => setPlanId(plan.id)}
              >
                <strong>{plan.original_filename}</strong>
                <span className={`status-pill ${plan.processing_status === 'ready' ? 'status-completed' : ''}`} style={{ marginLeft: 8 }}>
                  {STATUS_LABELS[plan.processing_status] || plan.processing_status}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
        <input type="file" accept=".pdf" onChange={(event) => setPlanFile(event.target.files?.[0] || null)} />
        <button type="button" className="btn btn-secondary" disabled={!planFile || loading} onClick={onUploadPlan}>
          Upload Plan
        </button>
      </div>

      {planDetail && (
        <div style={{ marginTop: 12 }}>
          <p className="muted">Page count: {planDetail.page_count}</p>
          {planDetail.pages?.length > 1 && (
            <select value={pageNumber} onChange={(event) => setPageNumber(Number(event.target.value))}>
              {planDetail.pages.map((page) => (
                <option key={page.id} value={page.page_number}>
                  Page {page.page_number}
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {workflow.stages.plans.status !== 'complete' && (
        <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>{workflow.stages.plans.reason}</p>
      )}
    </div>
  )
}
