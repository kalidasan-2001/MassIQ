import React from 'react'
import { STAGE_ORDER } from './deriveWorkflowStages'

const STAGE_LABELS = {
  project: 'Project',
  plans: 'Plans',
  plan_preparation: 'Plan Preparation',
  legend: 'Legend',
  materials: 'Materials',
  analysis: 'Analysis',
  review: 'Review',
  results: 'Results',
}

const STATUS_LABELS = {
  complete: 'Complete',
  in_progress: 'In progress',
  blocked: 'Blocked',
}

/**
 * R9 section 5/28: one clean stage navigation showing current/completed/
 * available/blocked -- status is always a text label, never color alone.
 * Blocked stages remain clickable (R9 section 7: "do not simply hide
 * blocked stages") so the user can see *why*, not just that they can't
 * proceed. "Project" has no dedicated content pane (the project/plan/page
 * picker above this nav is always visible), so it is shown for
 * orientation only, not clickable.
 */
export default function WorkflowNav({ stages, currentStage, onSelectStage }) {
  return (
    <nav className="workflow-nav" aria-label="Project workflow stages" data-testid="workflow-nav">
      <ul style={{ display: 'flex', gap: 8, flexWrap: 'wrap', listStyle: 'none', padding: 0, margin: 0 }}>
        {STAGE_ORDER.map((key) => {
          const stage = stages[key] || { status: 'blocked', reason: null }
          const isCurrent = key === currentStage
          const isNavigable = key !== 'project'
          return (
            <li key={key}>
              <button
                type="button"
                className="btn btn-secondary"
                aria-current={isCurrent ? 'step' : undefined}
                disabled={!isNavigable}
                onClick={() => isNavigable && onSelectStage?.(key)}
                data-testid={`workflow-stage-${key}`}
                style={{
                  borderColor: isCurrent ? 'var(--color-accent)' : undefined,
                  opacity: isNavigable ? 1 : 0.75,
                }}
              >
                <span>{STAGE_LABELS[key]}</span>
                <span
                  className={`status-pill ${stage.status === 'complete' ? 'status-completed' : ''}`}
                  style={{ marginLeft: 8 }}
                  data-testid={`workflow-stage-status-${key}`}
                >
                  {STATUS_LABELS[stage.status]}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
