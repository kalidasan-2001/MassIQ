import React from 'react'
import PatternLibraryPanel from '../legend/PatternLibraryPanel'

/**
 * R9 Materials stage: the R5 Project Pattern Library, presented as its
 * own stage. Not a hard gate for Analysis (a DetectionRun can reference a
 * confirmed LegendEntry directly) -- see docs/architecture/
 * PRODUCT_WORKFLOW.md. "Library suggests, user confirms": this stage is
 * a read-only browse view, the "Add to library" action itself lives on
 * the Legend stage right after a pattern's features are computed.
 */
export default function MaterialsStage({ projectId, workflow, libraryVersion }) {
  const stage = workflow.stages.materials
  return (
    <div>
      {stage.status !== 'complete' && (
        <p className="muted" style={{ marginBottom: 8 }} data-testid="stage-blocked-reason">{stage.reason}</p>
      )}
      <PatternLibraryPanel projectId={projectId} refreshKey={libraryVersion} />
    </div>
  )
}
