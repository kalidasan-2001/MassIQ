import React from 'react'
import UploadPanel from './components/UploadPanel'
import ProjectWorkflow from './features/workflow/ProjectWorkflow'

export default function App() {
  return (
    <div className="app-shell">
      <header className="hero">
        <div className="hero-copy">
          <p className="eyebrow">MassIQ</p>
          <h1>Construction quantity takeoff</h1>
          <p className="lede">
            Create a project, upload a floor plan, confirm scale, build a legend, analyze hatch
            patterns, review the detected regions, and export an authoritative quantity report.
          </p>
        </div>
      </header>
      <main className="main-content">
        <ProjectWorkflow />

        {/* Legacy single-session tool: predates the persisted Project/Plan
            workflow above and keeps its own independent state (nothing
            here is saved to a Project). Kept for the workflows it still
            covers on its own -- not the primary path for new work. See
            docs/architecture/R9_WORKFLOW_AUDIT.md's KEEP/ADAPT/DEPRECATE/
            REMOVE classification for why this stays (DEPRECATE, not
            removed -- legacy-workflow.spec.js and invalid-upload.spec.js
            still exercise it end to end, and R9 does not remove
            functionality without proving nothing depends on it). */}
        <section className="card panel" style={{ marginTop: 24 }}>
          <h2>Legacy single-session tool</h2>
          <p className="muted">
            An older, standalone quantity-takeoff flow that does not save a Project -- everything
            here is lost on refresh. Prefer the Project Workflow above for new work.
          </p>
        </section>
        <UploadPanel />
      </main>
    </div>
  )
}
