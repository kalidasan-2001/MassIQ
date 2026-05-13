import React, { useState } from 'react'
import api from '../api/api'

export default function HatchDetectionPanel({
  fileId,
  componentName,
  hatchSample,
  scale,
  detectionCount,
  onDetectionComplete,
  onClose,
}) {
  const [threshold, setThreshold] = useState(0.7)
  const [minRegionSize, setMinRegionSize] = useState(225)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const normalizeDetections = (detections) => {
    const pixelsPerMeter = Number(scale?.pixelsPerMeter || 0)
    const pxPerSquareMeter = pixelsPerMeter > 0 ? pixelsPerMeter ** 2 : 0

    return detections.map((detection, index) => {
      const width = Number(detection?.w ?? detection?.bbox?.width ?? 0)
      const height = Number(detection?.h ?? detection?.bbox?.height ?? 0)
      const x = Number(detection?.x ?? detection?.bbox?.x ?? 0)
      const y = Number(detection?.y ?? detection?.bbox?.y ?? 0)
      const areaPx = Math.max(0, width * height)

      return {
        id: detection?.id || `det-${index + 1}`,
        x,
        y,
        w: width,
        h: height,
        bbox: { x, y, width, height },
        confidence: Number(detection?.confidence ?? 0),
        area_m2: pxPerSquareMeter ? areaPx / pxPerSquareMeter : 0,
        status: 'pending',
      }
    })
  }

  const runDetection = async () => {
    if (!hatchSample?.hatch_sample_id) {
      setError('Hatch sample not found. Please select a hatch sample from the legend first.')
      return
    }
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const response = await api.post('/detect-hatch', {
        file_id: fileId,
        component_name: componentName,
        hatch_sample_id: hatchSample.hatch_sample_id,
        pixels_per_meter: scale?.pixelsPerMeter ?? null,
        threshold,
        min_region_size: minRegionSize,
        merge_nearby_detections: true,
        remove_small_noise: true,
      })
      const detections = normalizeDetections(response.data?.detections || [])
      onDetectionComplete?.(detections, {
        component: componentName,
        threshold,
        total: detections.length,
      })
      if (detections.length === 0) {
        setMessage('No detections found. Adjust the sample or threshold and try again.')
      } else {
        setMessage(`Backend returned ${detections.length} detection(s). Review them below.`)
      }
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message || 'Detection failed.'
      if (err?.response?.status === 404 && String(detail).toLowerCase().includes('hatch sample')) {
        setError('Hatch sample not found. Please select a hatch sample from the legend first.')
      } else {
        setError(detail)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card panel">
      <h3>Automatic Component Detection</h3>
      <p className="muted">
        The frontend sends the selected hatch sample to the backend, then shows the backend
        detections for review before any manual correction step.
      </p>
      <div className="field">
        <label>Selected component</label>
        <input value={componentName} readOnly />
      </div>
      <div className="field">
        <label>Similarity threshold: {threshold.toFixed(2)}</label>
        <input
          type="range"
          min="0.3"
          max="1"
          step="0.05"
          value={threshold}
          onChange={(event) => setThreshold(Number(event.target.value))}
        />
      </div>
      <div className="field">
        <label>Minimum region size: {minRegionSize} px</label>
        <input
          type="range"
          min="100"
          max="2500"
          step="25"
          value={minRegionSize}
          onChange={(event) => setMinRegionSize(Number(event.target.value))}
        />
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <button className="btn" disabled={loading} onClick={runDetection}>
          {loading ? 'Searching for matching component areas...' : 'Auto Detect Selected Component'}
        </button>
        <button className="btn btn-secondary" onClick={onClose}>
          Close
        </button>
      </div>
      <p className="muted" style={{ marginTop: 12 }}>
        Current reviewed detection count: <strong>{detectionCount}</strong>
      </p>
      {message && <p className="muted">{message}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  )
}
