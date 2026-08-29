import { describe, expect, it } from 'vitest'
import { deriveWorkflowStages, pickCurrentStage, isEntryInLibrary } from './deriveWorkflowStages'

const baseArgs = {
  hasProject: true,
  plans: [],
  hasPlanSelected: false,
  planScale: null,
  pageLegendEntries: [],
  activeEntryConfirmed: false,
  hatchFeatures: null,
  libraryEntries: [],
  detectionRun: null,
  detectedRegions: [],
  quantityResult: null,
}

describe('deriveWorkflowStages', () => {
  it('blocks everything downstream of Project when there is no project', () => {
    const stages = deriveWorkflowStages({ ...baseArgs, hasProject: false })
    expect(stages.project.status).toBe('blocked')
  })

  it('marks Plans in_progress until a READY plan exists', () => {
    const noPlans = deriveWorkflowStages(baseArgs)
    expect(noPlans.plans.status).toBe('in_progress')

    const withDraftPlan = deriveWorkflowStages({ ...baseArgs, plans: [{ processing_status: 'uploaded' }] })
    expect(withDraftPlan.plans.status).toBe('in_progress')

    const withReadyPlan = deriveWorkflowStages({ ...baseArgs, plans: [{ processing_status: 'ready' }] })
    expect(withReadyPlan.plans.status).toBe('complete')
  })

  it('blocks Plan Preparation and Legend until a plan is selected', () => {
    const stages = deriveWorkflowStages(baseArgs)
    expect(stages.plan_preparation.status).toBe('blocked')
    expect(stages.legend.status).toBe('blocked')
  })

  it('Plan Preparation completes once a scale is confirmed', () => {
    const noScale = deriveWorkflowStages({ ...baseArgs, hasPlanSelected: true })
    expect(noScale.plan_preparation.status).toBe('in_progress')

    const withScale = deriveWorkflowStages({ ...baseArgs, hasPlanSelected: true, planScale: { method: 'declared_scale' } })
    expect(withScale.plan_preparation.status).toBe('complete')
  })

  it('Legend completes once a legend entry is confirmed for the page', () => {
    const stages = deriveWorkflowStages({
      ...baseArgs,
      hasPlanSelected: true,
      pageLegendEntries: [{ status: 'confirmed' }],
    })
    expect(stages.legend.status).toBe('complete')
  })

  it('Analysis stays blocked without confirmed, feature-computed legend entry -- Materials is not a hard gate', () => {
    const stages = deriveWorkflowStages({
      ...baseArgs,
      hasPlanSelected: true,
      pageLegendEntries: [{ status: 'confirmed' }],
      activeEntryConfirmed: true,
      hatchFeatures: null,
    })
    expect(stages.analysis.status).toBe('blocked')

    const withFeatures = deriveWorkflowStages({
      ...baseArgs,
      hasPlanSelected: true,
      pageLegendEntries: [{ status: 'confirmed' }],
      activeEntryConfirmed: true,
      hatchFeatures: { feature_version: '1.0' },
      libraryEntries: [], // deliberately empty -- library membership must not gate Analysis
    })
    expect(withFeatures.analysis.status).toBe('in_progress')
  })

  it('Analysis completes once a DetectionRun is completed', () => {
    const stages = deriveWorkflowStages({
      ...baseArgs,
      hasPlanSelected: true,
      pageLegendEntries: [{ status: 'confirmed' }],
      activeEntryConfirmed: true,
      hatchFeatures: { feature_version: '1.0' },
      detectionRun: { status: 'completed' },
    })
    expect(stages.analysis.status).toBe('complete')
  })

  it('Review stays blocked until Analysis completes, then reflects pending candidate count', () => {
    const analysisIncomplete = deriveWorkflowStages(baseArgs)
    expect(analysisIncomplete.review.status).toBe('blocked')

    const pending = deriveWorkflowStages({
      ...baseArgs,
      hasPlanSelected: true,
      pageLegendEntries: [{ status: 'confirmed' }],
      activeEntryConfirmed: true,
      hatchFeatures: { feature_version: '1.0' },
      detectionRun: { status: 'completed' },
      detectedRegions: [{ status: 'candidate' }, { status: 'accepted' }],
    })
    expect(pending.review.status).toBe('in_progress')
    expect(pending.review.reason).toContain('1 still need a decision')

    const decided = deriveWorkflowStages({
      ...baseArgs,
      hasPlanSelected: true,
      pageLegendEntries: [{ status: 'confirmed' }],
      activeEntryConfirmed: true,
      hatchFeatures: { feature_version: '1.0' },
      detectionRun: { status: 'completed' },
      detectedRegions: [{ status: 'accepted' }, { status: 'rejected' }],
    })
    expect(decided.review.status).toBe('complete')
  })

  it('Results reflects the current quantity result status', () => {
    expect(deriveWorkflowStages(baseArgs).results.status).toBe('blocked')
    expect(deriveWorkflowStages({ ...baseArgs, quantityResult: { status: 'draft' } }).results.status).toBe('in_progress')
    expect(deriveWorkflowStages({ ...baseArgs, quantityResult: { status: 'confirmed' } }).results.status).toBe('complete')
  })
})

describe('pickCurrentStage', () => {
  it('never advances into a still-blocked stage just because an earlier one completed', () => {
    // Legend just confirmed, features not computed yet -- Analysis is
    // blocked. Must stay on 'legend', not jump into the blocked stage.
    const stages = deriveWorkflowStages({
      ...baseArgs,
      plans: [{ processing_status: 'ready' }],
      hasPlanSelected: true,
      pageLegendEntries: [{ status: 'confirmed' }],
      activeEntryConfirmed: true,
      hatchFeatures: null,
    })
    expect(pickCurrentStage(stages)).toBe('legend')
  })

  it('advances to Analysis once features are computed and it becomes actionable', () => {
    const stages = deriveWorkflowStages({
      ...baseArgs,
      plans: [{ processing_status: 'ready' }],
      hasPlanSelected: true,
      pageLegendEntries: [{ status: 'confirmed' }],
      activeEntryConfirmed: true,
      hatchFeatures: { feature_version: '1.0' },
    })
    expect(pickCurrentStage(stages)).toBe('analysis')
  })

  it('advances to Review immediately once Analysis completes', () => {
    const stages = deriveWorkflowStages({
      ...baseArgs,
      plans: [{ processing_status: 'ready' }],
      hasPlanSelected: true,
      pageLegendEntries: [{ status: 'confirmed' }],
      activeEntryConfirmed: true,
      hatchFeatures: { feature_version: '1.0' },
      detectionRun: { status: 'completed' },
      detectedRegions: [{ status: 'candidate' }],
    })
    expect(pickCurrentStage(stages)).toBe('review')
  })

  it('stays on Review when nothing further is actionable (Results blocked, not in_progress)', () => {
    const stages = deriveWorkflowStages({
      ...baseArgs,
      plans: [{ processing_status: 'ready' }],
      hasPlanSelected: true,
      pageLegendEntries: [{ status: 'confirmed' }],
      activeEntryConfirmed: true,
      hatchFeatures: { feature_version: '1.0' },
      detectionRun: { status: 'completed' },
      detectedRegions: [{ status: 'accepted' }],
    })
    expect(pickCurrentStage(stages)).toBe('review')
  })

  it('never auto-advances into Plan Preparation or Materials (not in the auto-advance chain)', () => {
    const stages = deriveWorkflowStages({ ...baseArgs, plans: [{ processing_status: 'ready' }] })
    expect(pickCurrentStage(stages)).not.toBe('plan_preparation')
    expect(pickCurrentStage(stages)).not.toBe('materials')
  })
})

describe('isEntryInLibrary', () => {
  it('is false with no active entry', () => {
    expect(isEntryInLibrary(null, [{ source_legend_entry_id: 'a' }])).toBe(false)
  })

  it('is false when the library has no matching entry', () => {
    expect(isEntryInLibrary({ id: 'a' }, [{ source_legend_entry_id: 'b' }])).toBe(false)
  })

  it('is true once the library list contains a matching source_legend_entry_id -- survives a refresh, not a session flag', () => {
    expect(isEntryInLibrary({ id: 'a' }, [{ source_legend_entry_id: 'a' }])).toBe(true)
  })
})
