import React from 'react'
import DetectionRunPanel from '../legend/DetectionRunPanel'

/**
 * R9 Analysis stage: R6 Detection V2, presented as its own stage. Makes
 * the REFERENCE_FEATURE_VERSION_OUTDATED guard actionable (R9 section
 * 15) instead of dumping the raw backend string -- the structured error
 * detail (routes/detection_runs.py) already carries a friendly message;
 * this adds a direct path back to Legend to recompute, without silently
 * recomputing on the user's behalf.
 */
export default function AnalysisStage({ workflow, onGoToStage }) {
  const stage = workflow.stages.analysis

  if (stage.status === 'blocked') {
    return (
      <div className="card panel">
        <h3>Analysis</h3>
        <p className="muted" data-testid="stage-blocked-reason">{stage.reason}</p>
      </div>
    )
  }

  return (
    <div className="card panel">
      <DetectionRunPanel
        run={workflow.detectionRun}
        busy={workflow.detectionBusy}
        disabled={!workflow.activeEntryId}
        onRunDetection={workflow.handleRunDetection}
      />
      {workflow.featureVersionOutdated && (
        <div className="error" style={{ marginTop: 10 }} data-testid="feature-version-outdated-notice">
          <p>{workflow.actionError}</p>
          <button type="button" className="btn btn-secondary" onClick={() => onGoToStage?.('legend')}>
            Go to Legend to recompute
          </button>
        </div>
      )}
      {!workflow.featureVersionOutdated && workflow.actionError && <p className="error">{workflow.actionError}</p>}
    </div>
  )
}
