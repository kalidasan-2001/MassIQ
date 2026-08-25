import React from 'react'
import UploadPanel from './components/UploadPanel'
import LegendFeaturePage from './features/legend/LegendFeaturePage'

export default function App() {
  return (
    <div className="app-shell">
      <header className="hero">
        <div className="hero-copy">
          <p className="eyebrow">MassIQ</p>
          <h1>Business MVP for automated quantity takeoff</h1>
          <p className="lede">
            Upload a floor plan, confirm scale, review automatic component detection, confirm
            height, and export a quantity report.
          </p>
        </div>
      </header>
      <main className="main-content">
        <UploadPanel />
        {/* R3: additive only -- the persisted Project/Plan/Legend workflow
            lives entirely separately from the legacy MVP flow above. */}
        <LegendFeaturePage />
      </main>
    </div>
  )
}
