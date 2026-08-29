import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import WorkflowNav from './WorkflowNav'

const stages = {
  project: { status: 'complete', reason: null },
  plans: { status: 'complete', reason: null },
  plan_preparation: { status: 'in_progress', reason: 'Confirm the drawing scale for this page.' },
  legend: { status: 'in_progress', reason: 'Select a hatch and its legend description, then confirm the material.' },
  materials: { status: 'blocked', reason: 'Compute hatch features on a confirmed legend entry to enable this.' },
  analysis: { status: 'blocked', reason: 'Analysis is available after you confirm at least one legend material and compute its hatch features.' },
  review: { status: 'blocked', reason: 'Run analysis first to get candidate regions to review.' },
  results: { status: 'blocked', reason: 'Calculate and confirm the quantity to see it in Results.' },
}

describe('WorkflowNav', () => {
  it('renders all 8 stages with a text status label, not color alone', () => {
    render(<WorkflowNav stages={stages} currentStage="legend" onSelectStage={vi.fn()} />)
    expect(screen.getByTestId('workflow-stage-status-materials')).toHaveTextContent('Blocked')
    expect(screen.getByTestId('workflow-stage-status-plans')).toHaveTextContent('Complete')
    expect(screen.getByTestId('workflow-stage-status-legend')).toHaveTextContent('In progress')
  })

  it('marks the current stage with aria-current', () => {
    render(<WorkflowNav stages={stages} currentStage="legend" onSelectStage={vi.fn()} />)
    expect(screen.getByTestId('workflow-stage-legend')).toHaveAttribute('aria-current', 'step')
    expect(screen.getByTestId('workflow-stage-analysis')).not.toHaveAttribute('aria-current')
  })

  it('blocked stages remain clickable so the user can see why, not just that they are blocked', async () => {
    const user = userEvent.setup()
    const onSelectStage = vi.fn()
    render(<WorkflowNav stages={stages} currentStage="legend" onSelectStage={onSelectStage} />)
    await user.click(screen.getByTestId('workflow-stage-analysis'))
    expect(onSelectStage).toHaveBeenCalledWith('analysis')
  })

  it('the Project stage has no dedicated pane and is not clickable', async () => {
    const user = userEvent.setup()
    const onSelectStage = vi.fn()
    render(<WorkflowNav stages={stages} currentStage="legend" onSelectStage={onSelectStage} />)
    expect(screen.getByTestId('workflow-stage-project')).toBeDisabled()
    await user.click(screen.getByTestId('workflow-stage-project'))
    expect(onSelectStage).not.toHaveBeenCalled()
  })
})
