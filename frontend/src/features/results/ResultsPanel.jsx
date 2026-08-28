import React, { useEffect, useState } from 'react'
import * as legendApi from '../legend/api'

const round = (value, decimals) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  const factor = 10 ** decimals
  return (Math.round(Number(value) * factor) / factor).toFixed(decimals)
}

/** Extracts the filename the backend already sanitized/chose out of a
 * real Content-Disposition response header -- never hardcoded here, and
 * never constructed client-side (R8 section 25: backend generates the
 * workbook AND names it; the frontend only downloads it). */
function filenameFromContentDisposition(header, fallback) {
  const match = /filename="?([^"]+)"?/.exec(header || '')
  return match ? match[1] : fallback
}

/**
 * R8: project-level Results & Export view -- the final stage of the
 * intended MassIQ workflow (Project -> Plans -> ... -> Results). Reads
 * only R7's authoritative, persisted QuantityResults; never computes its
 * own area/volume. Deliberately functional (R8 section 22 -- no major
 * navigation redesign), mirrors PatternLibraryPanel.jsx's own
 * project-level-panel shape.
 */
export default function ResultsPanel({ projectId, refreshKey }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expandedId, setExpandedId] = useState(null)
  const [confirmedCount, setConfirmedCount] = useState(0)
  const [exportBusy, setExportBusy] = useState(false)
  const [exportStatus, setExportStatus] = useState('')

  const refresh = () => {
    if (!projectId) return
    setLoading(true)
    setError('')
    Promise.all([legendApi.listResults(projectId), legendApi.exportPreflight(projectId)])
      .then(([results, preflight]) => {
        setRows(results)
        setConfirmedCount(preflight.confirmed_count)
      })
      .catch((err) => setError(err?.response?.data?.detail || err.message || 'Failed to load results.'))
      .finally(() => setLoading(false))
  }

  useEffect(refresh, [projectId, refreshKey])

  const handleExport = async () => {
    setExportBusy(true)
    setExportStatus('')
    try {
      const response = await legendApi.exportResults(projectId)
      const filename = filenameFromContentDisposition(
        response.headers['content-disposition'],
        'MassIQ_quantities.xlsx'
      )
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      const url = window.URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.URL.revokeObjectURL(url)
      setExportStatus('Export downloaded.')
    } catch (err) {
      setExportStatus(err?.response?.data?.detail || err.message || 'Export failed.')
    } finally {
      setExportBusy(false)
    }
  }

  if (!projectId) return null

  return (
    <div className="card panel" style={{ marginTop: 16 }} data-testid="results-panel">
      <h3>Results</h3>
      <p className="muted" style={{ marginBottom: 10 }}>
        Every confirmed and draft quantity for this project, sourced directly from the persisted, backend-computed
        QuantityResult -- never recalculated here.
      </p>

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <button type="button" className="btn btn-secondary" onClick={refresh} disabled={loading}>
          Refresh
        </button>
        <button
          type="button"
          className="btn"
          disabled={exportBusy || confirmedCount === 0}
          onClick={handleExport}
          data-testid="export-results-btn"
        >
          {exportBusy ? 'Exporting...' : `Export confirmed quantities (${confirmedCount})`}
        </button>
      </div>
      {confirmedCount === 0 && rows.length > 0 && (
        <p className="muted" style={{ marginTop: 6, fontSize: 13 }} data-testid="export-disabled-hint">
          No confirmed quantities yet -- draft results are not included in export.
        </p>
      )}
      {exportStatus && <p className="muted" style={{ marginTop: 6 }} data-testid="export-status">{exportStatus}</p>}
      {error && <p className="error">{error}</p>}

      {!loading && rows.length === 0 && (
        <p className="muted" style={{ marginTop: 10 }} data-testid="results-empty">
          No quantities yet -- run detection, review, and calculate a quantity to see it here.
        </p>
      )}

      {rows.length > 0 && (
        <table style={{ marginTop: 12, width: '100%' }} data-testid="results-table">
          <thead>
            <tr>
              <th>Plan</th>
              <th>Page</th>
              <th>Material</th>
              <th>Area [m&sup2;]</th>
              <th>Dimension [m]</th>
              <th>Volume [m&sup3;]</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <React.Fragment key={row.quantity_result_id}>
                <tr data-testid="result-row">
                  <td>{row.plan_name}</td>
                  <td>{row.page_number}</td>
                  <td>{row.material_name}</td>
                  <td data-testid="result-area">{round(row.area_m2, 2)}</td>
                  <td>{round(row.confirmed_dimension_m, 3)}</td>
                  <td data-testid="result-volume">{round(row.volume_m3, 3)}</td>
                  <td>
                    <span
                      className={`status-pill ${row.status === 'confirmed' ? 'status-completed' : ''}`}
                      data-testid="result-status"
                    >
                      {row.status === 'confirmed' ? 'Confirmed' : 'Draft'}
                    </span>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      onClick={() => setExpandedId(expandedId === row.quantity_result_id ? null : row.quantity_result_id)}
                      data-testid="result-details-btn"
                    >
                      {expandedId === row.quantity_result_id ? 'Hide' : 'Details'}
                    </button>
                  </td>
                </tr>
                {expandedId === row.quantity_result_id && (
                  <tr data-testid="result-details-panel">
                    <td colSpan={8}>
                      <div className="muted" style={{ fontSize: 13, padding: '6px 0' }}>
                        <div>Material: {row.material_name}{row.material_code ? ` (${row.material_code})` : ''}</div>
                        <div>Plan: {row.plan_name}</div>
                        <div>Area: {round(row.area_m2, 2)} m&sup2;</div>
                        <div>Thickness: {round(row.confirmed_dimension_m, 3)} m</div>
                        <div>Volume: {round(row.volume_m3, 3)} m&sup3;</div>
                        <div>Status: {row.status === 'confirmed' ? 'Confirmed' : 'Draft'}</div>
                        <div>Calculation version: {row.calculation_version}</div>
                        <div>Accepted regions: {row.accepted_region_count}</div>
                        <div>Rejected regions: {row.rejected_region_count}</div>
                        <div>Manual additions: {row.manual_add_count}</div>
                        <div>Manual subtractions: {row.manual_subtract_count}</div>
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
