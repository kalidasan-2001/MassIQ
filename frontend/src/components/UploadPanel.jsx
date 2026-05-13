import React, { useEffect, useState } from 'react'
import api from '../api/api'
import PlanViewer from './PlanViewer'

const LAST_UPLOAD_KEY = 'massiq-last-upload-result'

export default function UploadPanel() {
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    const saved = localStorage.getItem(LAST_UPLOAD_KEY)
    if (!saved) return
    try {
      setResult(JSON.parse(saved))
    } catch {
      localStorage.removeItem(LAST_UPLOAD_KEY)
    }
  }, [])

  const upload = async () => {
    if (!file) {
      setError('Please select a PDF file to upload.')
      return
    }
    const form = new FormData()
    form.append('file', file, file.name)
    setLoading(true)
    setError('')
    try {
      const response = await api.post('/upload-pdf', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setResult(response.data)
      localStorage.setItem(LAST_UPLOAD_KEY, JSON.stringify(response.data))
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Upload failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="card panel">
      <div className="workflow-grid" style={{ marginBottom: 20 }}>
        {[
          'Plan',
          'Scale',
          'Legend',
          'Detection',
          'Review',
          'Height',
          'Quantity',
          'Export',
        ].map((step, index) => (
          <div className="workflow-step" key={step}>
            <strong>{index + 1}. {step}</strong>
            <div className="status-pill">{index === 0 ? 'In progress' : 'Not started'}</div>
          </div>
        ))}
      </div>

      <div className="field">
        <label>Floor plan PDF</label>
        <input type="file" accept=".pdf" onChange={(event) => setFile(event.target.files?.[0] || null)} />
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <button className="btn" onClick={upload} disabled={loading}>
          {loading ? 'Uploading...' : 'Upload Floor Plan PDF'}
        </button>
        <button
          className="btn btn-secondary"
          onClick={() => {
            setResult(null)
            setFile(null)
            localStorage.removeItem(LAST_UPLOAD_KEY)
          }}
        >
          Clear Project
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {result && (
        <div style={{ marginTop: 24 }}>
          <p className="muted">Plan ready. File ID: <strong>{result.file_id}</strong></p>
          <PlanViewer file_id={result.file_id} page_image_url={result.page_image_url} />
        </div>
      )}
    </section>
  )
}
