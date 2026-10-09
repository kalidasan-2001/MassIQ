import React from 'react'
import ScaleConfirmationPanel from '../legend/ScaleConfirmationPanel'

/**
 * R9 Plan Preparation stage: scale confirmation, now reachable as soon as
 * a plan page is selected -- the pre-R9 UI accidentally required a
 * completed Detection run first, purely because the form was dropped
 * inside QuantityPanel.jsx (see docs/architecture/R9_WORKFLOW_AUDIT.md).
 * The backend never had that dependency (PUT .../scale only needs a
 * plan page).
 */
export default function PlanPreparationStage({ workflow }) {
  const stage = workflow.stages.plan_preparation

  if (stage.status === 'blocked') {
    return (
      <div className="card panel">
        <h3>Plan Preparation</h3>
        <p className="muted" data-testid="stage-blocked-reason">{stage.reason}</p>
      </div>
    )
  }

  return (
    <div className="card panel">
      <ScaleConfirmationPanel
        scale={workflow.planScale}
        busy={workflow.quantityBusy}
        disabled={false}
        onConfirmDeclaredScale={workflow.handleConfirmDeclaredScale}
        onConfirmCalibratedScale={workflow.handleConfirmCalibratedScale}
      />
    </div>
  )
}
