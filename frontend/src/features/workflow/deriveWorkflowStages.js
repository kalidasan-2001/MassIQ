/**
 * R9: derives per-stage workflow status from persisted-truth data the app
 * already fetches for its own rendering -- no second workflow database,
 * no invented completion rules. See docs/architecture/PRODUCT_WORKFLOW.md
 * for the rationale behind each rule (verified against the actual
 * SQLAlchemy status enums, not guessed).
 *
 * Scope note: like the rest of the current UI, this operates on one
 * selected Plan Page at a time -- Plan Preparation/Legend/Materials/
 * Analysis/Review are all evaluated for the *currently selected* plan
 * page, not aggregated across the whole project. Results is the one
 * project-wide exception (it already lists every plan/page).
 *
 * Status vocabulary matches R9 section 20's example response:
 * 'complete' | 'in_progress' | 'blocked'.
 */
export const STAGE_ORDER = [
  'project',
  'plans',
  'plan_preparation',
  'legend',
  'materials',
  'analysis',
  'review',
  'results',
]

// Materials and Plan Preparation are deliberately excluded from
// auto-advance. Materials is not a hard gate for Analysis (a DetectionRun
// can reference a LegendEntry directly, with no PatternLibraryEntry
// involved -- see DetectionRun's reference columns). Plan Preparation is
// not a hard gate for Legend or Analysis either -- only Review's
// "Calculate Quantity" action actually requires a confirmed scale (and
// that control is independently disabled until one exists). Numbered
// display order (R9 section 5) is a product-communication choice; this
// order is the actual dependency graph, so the nav doesn't stall on a
// stage nothing downstream is truly blocked by.
const AUTO_ADVANCE_ORDER = ['plans', 'legend', 'analysis', 'review', 'results']

export function deriveWorkflowStages({
  hasProject,
  plans = [],
  hasPlanSelected,
  planScale,
  pageLegendEntries = [],
  activeEntryConfirmed,
  hatchFeatures,
  libraryEntries = [],
  detectionRun,
  detectedRegions = [],
  quantityResult,
}) {
  const stages = {}

  stages.project = hasProject
    ? { status: 'complete', reason: null }
    : { status: 'blocked', reason: 'Create or select a project to begin.' }

  const hasReadyPlan = plans.some((plan) => plan.processing_status === 'ready')
  stages.plans = hasReadyPlan
    ? { status: 'complete', reason: null }
    : { status: 'in_progress', reason: 'Upload a construction plan to continue.' }

  if (!hasPlanSelected) {
    stages.plan_preparation = { status: 'blocked', reason: 'Select a plan and page first.' }
  } else if (planScale) {
    stages.plan_preparation = { status: 'complete', reason: null }
  } else {
    stages.plan_preparation = { status: 'in_progress', reason: 'Confirm the drawing scale for this page.' }
  }

  if (!hasPlanSelected) {
    stages.legend = { status: 'blocked', reason: 'Select a plan first.' }
  } else if (pageLegendEntries.some((entry) => entry.status === 'confirmed')) {
    stages.legend = { status: 'complete', reason: null }
  } else {
    stages.legend = {
      status: 'in_progress',
      reason: 'Select a hatch and its legend description, then confirm the material.',
    }
  }

  const hasComputedFeatures = stages.legend.status === 'complete' && activeEntryConfirmed && !!hatchFeatures
  if (libraryEntries.length > 0) {
    stages.materials = { status: 'complete', reason: null }
  } else if (hasComputedFeatures) {
    stages.materials = {
      status: 'in_progress',
      reason: 'Add this confirmed pattern to the Project Pattern Library for reuse (optional).',
    }
  } else {
    stages.materials = {
      status: 'blocked',
      reason: 'Compute hatch features on a confirmed legend entry to enable this.',
    }
  }

  if (!hasComputedFeatures) {
    stages.analysis = {
      status: 'blocked',
      reason: 'Analysis is available after you confirm at least one legend material and compute its hatch features.',
    }
  } else if (detectionRun?.status === 'completed') {
    stages.analysis = { status: 'complete', reason: null }
  } else {
    stages.analysis = { status: 'in_progress', reason: 'Run analysis to detect candidate regions on this page.' }
  }

  if (stages.analysis.status !== 'complete') {
    stages.review = { status: 'blocked', reason: 'Run analysis first to get candidate regions to review.' }
  } else {
    const pendingCount = detectedRegions.filter((region) => region.status === 'candidate').length
    stages.review =
      pendingCount === 0
        ? { status: 'complete', reason: null }
        : { status: 'in_progress', reason: `Review the detected regions -- ${pendingCount} still need a decision.` }
  }

  if (!quantityResult) {
    stages.results = { status: 'blocked', reason: 'Calculate and confirm the quantity to see it in Results.' }
  } else if (quantityResult.status === 'confirmed') {
    stages.results = { status: 'complete', reason: null }
  } else {
    stages.results = { status: 'in_progress', reason: 'Confirm the calculated quantity to finalize this result.' }
  }

  return stages
}

/** R9 audit fix: "already in library" derived from the fetched library
 * list (matched on source_legend_entry_id), not a session-only flag that
 * forgets across a refresh -- see useProjectWorkflowState.js. */
export function isEntryInLibrary(activeEntry, libraryEntries = []) {
  return !!activeEntry && libraryEntries.some((entry) => entry.source_legend_entry_id === activeEntry.id)
}

/**
 * The stage the nav should show as "current". Advances to the first
 * stage with real, actionable next work ('in_progress') -- but never
 * jumps *into* a stage that is still 'blocked' just because an earlier
 * stage completed (e.g. finishing Legend must not yank the user into a
 * still-blocked Analysis before hatch features are computed -- there
 * would be nothing to do there yet, and it would hide the Legend
 * controls, like "add to library", still relevant right after
 * confirming). When nothing further is actionable yet, stays on the
 * last completed stage instead of stalling on a blocked one.
 */
export function pickCurrentStage(stages) {
  const firstInProgress = AUTO_ADVANCE_ORDER.find((key) => stages[key]?.status === 'in_progress')
  if (firstInProgress) return firstInProgress
  const lastComplete = [...AUTO_ADVANCE_ORDER].reverse().find((key) => stages[key]?.status === 'complete')
  return lastComplete || AUTO_ADVANCE_ORDER[0]
}
