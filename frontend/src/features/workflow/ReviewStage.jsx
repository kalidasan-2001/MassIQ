import React from 'react'
import RegionReviewList from '../legend/RegionReviewList'
import ManualCorrectionPanel from '../legend/ManualCorrectionPanel'
import QuantityPanel from '../legend/QuantityPanel'

/**
 * R9 Review stage: accept/reject candidates, manual ADD/SUBTRACT, and the
 * calculated/confirmed quantity, all together -- R9 section 16/17 wants
 * the user to see quantity controls right where review happens, not
 * hunting elsewhere on the page.
 */
export default function ReviewStage({ workflow }) {
  const stage = workflow.stages.review

  if (stage.status === 'blocked') {
    return (
      <div className="card panel">
        <h3>Review</h3>
        <p className="muted" data-testid="stage-blocked-reason">{stage.reason}</p>
      </div>
    )
  }

  return (
    <>
      <div className="card panel">
        <h3>Review candidates</h3>
        <RegionReviewList
          regions={workflow.detectedRegions}
          busy={workflow.detectionBusy}
          onUpdateRegionStatus={workflow.handleUpdateRegionStatus}
        />
      </div>

      <div className="card panel" style={{ marginTop: 16 }}>
        <ManualCorrectionPanel
          mode={workflow.selection.mode === 'manual_add' || workflow.selection.mode === 'manual_subtract' ? workflow.selection.mode : null}
          corrections={workflow.manualCorrections}
          busy={workflow.quantityBusy}
          disabled={workflow.actionBusy}
          onStartAdd={() => workflow.selection.startMode('manual_add')}
          onStartSubtract={() => workflow.selection.startMode('manual_subtract')}
          onCancel={workflow.selection.cancelMode}
          onDeleteCorrection={workflow.handleDeleteManualCorrection}
        />
      </div>

      <div className="card panel" style={{ marginTop: 16 }}>
        <QuantityPanel
          scale={workflow.planScale}
          quantity={workflow.quantityResult}
          suggestedThicknessMm={workflow.activeEntry?.thickness_mm ?? null}
          busy={workflow.quantityBusy}
          disabled={false}
          reviewCounts={workflow.reviewCounts}
          onCalculate={workflow.handleCalculateQuantity}
          onConfirmResult={workflow.handleConfirmQuantityResult}
        />
      </div>
    </>
  )
}
