import React from 'react'
import * as legendApi from '../legend/api'
import LegendEntryList from '../legend/LegendEntryList'
import LegendEntryEditor from '../legend/LegendEntryEditor'

/**
 * R9 Legend stage: select hatch -> select description -> OCR -> correct
 * text -> confirm material -> compute features. Unchanged from the R3/R4
 * implementation -- just its own stage pane instead of always-visible
 * content in LegendWorkspace.jsx.
 */
export default function LegendStage({ projectId, planId, workflow }) {
  if (!planId) {
    return (
      <div className="card panel">
        <h3>Legend</h3>
        <p className="muted" data-testid="stage-blocked-reason">{workflow.stages.legend.reason}</p>
      </div>
    )
  }

  return (
    <>
      <LegendEntryList
        entries={workflow.entries}
        activeEntryId={workflow.activeEntryId}
        onSelect={workflow.setActiveEntryId}
        onCreateNew={workflow.handleCreateNew}
        creating={workflow.creating}
      />
      {workflow.entriesLoading && <p className="muted">Loading legend entries...</p>}
      {workflow.entriesError && <p className="error">{workflow.entriesError}</p>}
      <div style={{ marginTop: 16 }}>
        <LegendEntryEditor
          entry={workflow.activeEntry}
          patternCropSrc={
            workflow.activeEntry?.has_pattern_selection
              ? legendApi.patternCropUrl(projectId, planId, workflow.activeEntry.id, workflow.cropVersion)
              : null
          }
          descriptionCropSrc={
            workflow.activeEntry?.has_description_selection
              ? legendApi.descriptionCropUrl(projectId, planId, workflow.activeEntry.id, workflow.cropVersion)
              : null
          }
          busy={workflow.actionBusy}
          error={workflow.actionError}
          onRunOcr={workflow.handleRunOcr}
          onSaveCorrection={workflow.handleSaveCorrection}
          onConfirm={workflow.handleConfirm}
          hatchFeatures={workflow.hatchFeatures}
          featuresBusy={workflow.featuresBusy}
          onComputeFeatures={workflow.handleComputeFeatures}
          projectId={projectId}
          planId={planId}
          inLibrary={workflow.inLibrary}
          libraryBusy={workflow.libraryBusy}
          onAddToLibrary={workflow.handleAddToLibrary}
        />
      </div>
    </>
  )
}
