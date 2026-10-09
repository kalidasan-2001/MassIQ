import React from 'react'
import ResultsPanel from '../results/ResultsPanel'

/**
 * R9 Results stage: R8's project-level Results & Export view, as the
 * final workflow stage. Always shows every confirmed/draft quantity in
 * the project (not just the current plan page) -- the per-page "results"
 * derivation used for stage-nav status is a convenience hint, not a
 * restriction on what this view shows.
 */
export default function ResultsStage({ projectId, workflow, resultsVersion }) {
  const stage = workflow.stages.results
  return (
    <div>
      {stage.status !== 'complete' && (
        <p className="muted" style={{ marginBottom: 8 }} data-testid="stage-blocked-reason">{stage.reason}</p>
      )}
      <ResultsPanel projectId={projectId} refreshKey={resultsVersion} />
    </div>
  )
}
