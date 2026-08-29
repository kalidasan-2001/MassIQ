import React, { useEffect, useMemo, useState } from 'react'
import * as legendApi from '../legend/api'
import PlanCanvas from '../legend/PlanCanvas'
import LegendSelectionToolbar from '../legend/LegendSelectionToolbar'
import { useProjectWorkflowState } from './useProjectWorkflowState'
import { useWorkflowUrlState } from './useWorkflowUrlState'
import WorkflowNav from './WorkflowNav'
import PlansStage from './PlansStage'
import PlanPreparationStage from './PlanPreparationStage'
import LegendStage from './LegendStage'
import MaterialsStage from './MaterialsStage'
import AnalysisStage from './AnalysisStage'
import ReviewStage from './ReviewStage'
import ResultsStage from './ResultsStage'

// R9: rendered additively, in stage order, not switched exclusively --
// see the comment on ProjectWorkflow below for why. Each entry knows how
// to show its own blocked-reason message when its own prerequisite isn't
// met yet (R9 section 7: "do not simply hide blocked stages").
const STAGE_LIST = [
  ['plans', PlansStage],
  ['plan_preparation', PlanPreparationStage],
  ['legend', LegendStage],
  ['materials', MaterialsStage],
  ['analysis', AnalysisStage],
  ['review', ReviewStage],
  ['results', ResultsStage],
]

/**
 * R9: the canonical single-workflow shell -- Project -> Plans -> Plan
 * Preparation -> Legend -> Materials -> Analysis -> Review -> Results.
 * Replaces LegendFeaturePage.jsx (project/plan/page selection) and
 * LegendWorkspace.jsx (per-page orchestration): all of that state/those
 * handlers now live in useProjectWorkflowState, and this component is
 * just composition -- URL sync, project/plan/page pickers, the stage nav,
 * and rendering every stage's pane (each stage decides for itself
 * whether to show its blocked-reason message or its real controls) plus
 * the shared plan canvas.
 */
export default function ProjectWorkflow() {
  const [urlState, setUrlState] = useWorkflowUrlState()

  const [projects, setProjects] = useState([])
  const [newProjectName, setNewProjectName] = useState('')
  const [plans, setPlans] = useState([])
  const [planFile, setPlanFile] = useState(null)
  const [planDetail, setPlanDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [libraryVersion, setLibraryVersion] = useState(0)
  const [resultsVersion, setResultsVersion] = useState(0)
  const [manualStage, setManualStage] = useState(null)

  const projectId = urlState.projectId
  const planId = urlState.planId
  const pageNumber = urlState.pageNumber || 1

  const setProjectId = (value) => setUrlState({ projectId: value, planId: '', pageNumber: null, stage: '' })
  const setPlanId = (value) => setUrlState({ planId: value, pageNumber: null })
  const setPageNumber = (value) => setUrlState({ pageNumber: value })

  const refreshProjects = async () => {
    try {
      setProjects(await legendApi.listProjects())
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Failed to load projects.')
    }
  }

  useEffect(() => {
    refreshProjects()
  }, [])

  useEffect(() => {
    if (!projectId) {
      setPlans([])
      return
    }
    legendApi
      .listPlans(projectId)
      .then(setPlans)
      .catch((err) => setError(err?.response?.data?.detail || err.message || 'Failed to load plans.'))
  }, [projectId])

  useEffect(() => {
    if (!projectId || !planId) {
      setPlanDetail(null)
      return
    }
    legendApi
      .getPlanDetail(projectId, planId)
      .then((detail) => {
        setPlanDetail(detail)
        if (!urlState.pageNumber) {
          setUrlState({ pageNumber: detail.pages?.[0]?.page_number || 1 })
        }
      })
      .catch((err) => setError(err?.response?.data?.detail || err.message || 'Failed to load plan detail.'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, planId])

  const currentPage = planDetail?.pages?.find((page) => page.page_number === pageNumber)
  const previewUrl = projectId && planId ? legendApi.planPagePreviewUrl(projectId, planId, pageNumber) : null

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return
    setLoading(true)
    setError('')
    try {
      const project = await legendApi.createProject(newProjectName.trim())
      setNewProjectName('')
      await refreshProjects()
      setProjectId(project.id)
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Failed to create project.')
    } finally {
      setLoading(false)
    }
  }

  const handleUploadPlan = async () => {
    if (!planFile || !projectId) return
    setLoading(true)
    setError('')
    try {
      const plan = await legendApi.uploadPlan(projectId, planFile)
      setPlans(await legendApi.listPlans(projectId))
      setPlanId(plan.id)
      setPlanFile(null)
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Failed to upload plan. Only real, readable PDFs are accepted.')
    } finally {
      setLoading(false)
    }
  }

  const workflow = useProjectWorkflowState({
    projectId,
    planId,
    pageNumber,
    planPageId: currentPage?.id || null,
    plans,
    onLibraryChanged: () => setLibraryVersion((v) => v + 1),
    onResultsChanged: () => setResultsVersion((v) => v + 1),
  })

  // R9: every stage pane is rendered additively, in order -- not switched
  // exclusively. Detection/Review/Quantity used to all be simultaneously
  // reachable the instant their own prerequisite was met (no navigation
  // click), and every R3-R8 Playwright spec was written against that
  // continuous-visibility model. Gating rendering to "one active stage"
  // made completing one stage yank the next-incomplete stage's pane in
  // and unmount the one the user (and the existing test suite) was still
  // interacting with -- the opposite of "guided, not a one-way wizard"
  // (R9 section 8). Each stage component still shows its own
  // blocked-reason message when its own prerequisite isn't met (R9
  // section 7), so nothing is silently hidden -- it just isn't hidden by
  // *unmounting a sibling stage* either. WorkflowNav's `currentStage`
  // still highlights the most relevant next stage and scrolls to it.
  const goToStage = (key) => {
    setManualStage(key)
    document.getElementById(`stage-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const confirmedResultsHint = useMemo(() => {
    if (!projectId) return null
    return workflow.stages.results.status === 'complete'
      ? 'This page has a confirmed quantity -- see it in Results.'
      : null
  }, [projectId, workflow.stages.results.status])

  return (
    <section className="card panel" style={{ marginTop: 24 }} data-testid="project-workflow-root">
      <h2>Project Workflow</h2>
      <p className="muted">
        Project -&gt; Plans -&gt; Plan Preparation -&gt; Legend -&gt; Materials -&gt; Analysis -&gt; Review -&gt; Results.
      </p>

      <div className="workflow-grid" style={{ marginBottom: 16 }}>
        <div className="workflow-step">
          <strong>Project</strong>
          <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
            <select value={projectId} onChange={(event) => setProjectId(event.target.value)}>
              <option value="">Select a project...</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
            <input
              placeholder="New project name"
              value={newProjectName}
              onChange={(event) => setNewProjectName(event.target.value)}
            />
            <button type="button" className="btn btn-secondary" disabled={loading} onClick={handleCreateProject}>
              Create
            </button>
          </div>
          {projectId && (
            <p className="muted" style={{ marginTop: 8, fontSize: 13 }} data-testid="project-landing-summary">
              {plans.length} plan{plans.length === 1 ? '' : 's'} in this project.
              {confirmedResultsHint ? ` ${confirmedResultsHint}` : ''}
            </p>
          )}
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      {projectId && (
        <>
          <WorkflowNav stages={workflow.stages} currentStage={manualStage || workflow.currentStage} onSelectStage={goToStage} />

          <div className="two-col" style={{ marginTop: 16 }}>
            {previewUrl && currentPage ? (
              <PlanCanvas
                pageNumber={pageNumber}
                previewUrl={previewUrl}
                overlays={workflow.overlays}
                detectedRegions={workflow.detectedRegions}
                manualCorrections={workflow.manualCorrections}
                selection={workflow.selection}
                toolbar={
                  <LegendSelectionToolbar
                    mode={workflow.selection.mode}
                    disabled={!workflow.activeEntryId || workflow.actionBusy}
                    onStartPattern={() => workflow.selection.startMode('pattern')}
                    onStartDescription={() => workflow.selection.startMode('description')}
                    onCancel={workflow.selection.cancelMode}
                  />
                }
                hint={
                  !workflow.activeEntryId
                    ? 'Create or select a legend entry (right) to enable drawing a selection here.'
                    : null
                }
              />
            ) : (
              <div className="card panel">
                <p className="muted">Upload and select a plan page to see it here.</p>
              </div>
            )}

            <div>
              {STAGE_LIST.map(([key, StageComponent]) => (
                <div key={key} id={`stage-${key}`} style={{ marginTop: key === 'plans' ? 0 : 16 }}>
                  <StageComponent
                    projectId={projectId}
                    planId={planId}
                    pageNumber={pageNumber}
                    planDetail={planDetail}
                    plans={plans}
                    planFile={planFile}
                    setPlanFile={setPlanFile}
                    onUploadPlan={handleUploadPlan}
                    loading={loading}
                    setPlanId={setPlanId}
                    setPageNumber={setPageNumber}
                    workflow={workflow}
                    libraryVersion={libraryVersion}
                    resultsVersion={resultsVersion}
                    onGoToStage={goToStage}
                  />
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </section>
  )
}
