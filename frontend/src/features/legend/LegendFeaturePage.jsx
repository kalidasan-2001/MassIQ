import React, { useEffect, useState } from 'react'
import * as legendApi from './api'
import LegendWorkspace from './LegendWorkspace'

/**
 * R3's prerequisite that didn't exist anywhere in the app before this
 * release: a way to create/pick a persisted Project, upload/pick a Plan
 * through the *new* Plan API (not the legacy /upload-pdf path), and pick a
 * page -- then hand off to LegendWorkspace. Deliberately minimal/functional
 * (R3 scope explicitly excludes final visual design) and entirely
 * additive: nothing here is reachable from, or changes, UploadPanel.jsx /
 * PlanViewer.jsx's legacy MVP flow.
 */
export default function LegendFeaturePage() {
  const [projects, setProjects] = useState([])
  const [projectId, setProjectId] = useState('')
  const [newProjectName, setNewProjectName] = useState('')

  const [plans, setPlans] = useState([])
  const [planId, setPlanId] = useState('')
  const [planFile, setPlanFile] = useState(null)

  const [planDetail, setPlanDetail] = useState(null)
  const [pageNumber, setPageNumber] = useState(1)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

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
      setPlanId('')
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
        setPageNumber(detail.pages?.[0]?.page_number || 1)
      })
      .catch((err) => setError(err?.response?.data?.detail || err.message || 'Failed to load plan detail.'))
  }, [projectId, planId])

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

  const currentPage = planDetail?.pages?.find((page) => page.page_number === pageNumber)
  const previewUrl = projectId && planId ? legendApi.planPagePreviewUrl(projectId, planId, pageNumber) : null

  return (
    <section className="card panel" style={{ marginTop: 24 }}>
      <h2>Legend Workflow (R3)</h2>
      <p className="muted">
        Persisted Plan Page -&gt; select hatch pattern -&gt; select description -&gt; OCR -&gt; correct -&gt; confirm
        material -&gt; save LegendEntry. Uses the persisted Project/Plan pipeline, not the legacy upload above.
      </p>

      <div className="workflow-grid" style={{ marginBottom: 16 }}>
        <div className="workflow-step">
          <strong>1. Project</strong>
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
        </div>

        <div className="workflow-step">
          <strong>2. Plan</strong>
          <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
            <select value={planId} onChange={(event) => setPlanId(event.target.value)} disabled={!projectId}>
              <option value="">Select a plan...</option>
              {plans.map((plan) => (
                <option key={plan.id} value={plan.id}>
                  {plan.original_filename} ({plan.processing_status})
                </option>
              ))}
            </select>
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
            <input
              type="file"
              accept=".pdf"
              disabled={!projectId}
              onChange={(event) => setPlanFile(event.target.files?.[0] || null)}
            />
            <button type="button" className="btn btn-secondary" disabled={!planFile || loading} onClick={handleUploadPlan}>
              Upload Plan
            </button>
          </div>
        </div>

        <div className="workflow-step">
          <strong>3. Page</strong>
          {planDetail?.pages?.length > 1 ? (
            <select
              style={{ marginTop: 8 }}
              value={pageNumber}
              onChange={(event) => setPageNumber(Number(event.target.value))}
            >
              {planDetail.pages.map((page) => (
                <option key={page.id} value={page.page_number}>
                  Page {page.page_number}
                </option>
              ))}
            </select>
          ) : (
            <div className="status-pill" style={{ marginTop: 8 }}>
              {planDetail ? `Page ${pageNumber} of ${planDetail.page_count}` : 'Select a plan first'}
            </div>
          )}
        </div>
      </div>

      {error && <p className="error">{error}</p>}

      {previewUrl && currentPage && (
        <LegendWorkspace
          projectId={projectId}
          planId={planId}
          pageNumber={pageNumber}
          planPageId={currentPage.id}
          previewUrl={previewUrl}
        />
      )}
    </section>
  )
}
