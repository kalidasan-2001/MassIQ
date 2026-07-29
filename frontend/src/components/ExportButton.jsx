import React, { useState } from 'react'
import api from '../api/api'

export default function ExportButton(props) {
  const [status, setStatus] = useState('')

  const handleExport = async () => {
    setStatus('')
    try {
      const response = await api.post('/export-excel', {
        project_name: props.projectName,
        plan_name: props.planName,
        component: props.componentName,
        detection_method: props.detectionMethod,
        area_m2: Number(props.areaM2),
        accepted_detection_area_m2: Number(props.acceptedDetectionAreaM2 || props.areaM2 || 0),
        added_correction_area_m2: Number(props.addedCorrectionAreaM2 || 0),
        subtracted_correction_area_m2: Number(props.subtractedCorrectionAreaM2 || 0),
        height_m: Number(props.heightM),
        volume_m3: Number(props.volumeM3),
        deductions: Array.isArray(props.deductions) ? props.deductions : [],
        review_status: props.reviewStatus || 'Completed',
        notes: props.notes || '',
      }, {
        responseType: 'blob',
      })
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      const url = window.URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'massiq_quantity_report.xlsx'
      anchor.click()
      window.URL.revokeObjectURL(url)
      setStatus('Excel report exported successfully.')
    } catch (err) {
      setStatus(err?.response?.data?.detail || err.message || 'Export failed.')
    }
  }

  return (
    <div>
      <button className="btn" onClick={handleExport}>
        Export Quantity Report
      </button>
      {status && <p className="muted">{status}</p>}
    </div>
  )
}
