// R3: thin wrappers around the persisted Project/Plan/LegendEntry API,
// reusing the shared axios instance (src/api/api.js) -- same base URL,
// same timeout, same conventions the rest of the app already uses. This
// module is deliberately separate from the legacy legacy-MVP calls in
// HatchDetectionPanel.jsx/LegendAssistantPanel.jsx, which keep talking to
// the old filesystem-only /upload-pdf pipeline unchanged.
import api from '../../api/api'

// -- Project / Plan (prerequisite for the Legend workflow) -------------

export function listProjects() {
  return api.get('/api/projects').then((response) => response.data)
}

export function createProject(name) {
  return api.post('/api/projects', { name }).then((response) => response.data)
}

export function listPlans(projectId) {
  return api.get(`/api/projects/${projectId}/plans`).then((response) => response.data)
}

export function getPlanDetail(projectId, planId) {
  return api.get(`/api/projects/${projectId}/plans/${planId}`).then((response) => response.data)
}

export function uploadPlan(projectId, file) {
  const form = new FormData()
  form.append('file', file, file.name)
  return api
    .post(`/api/projects/${projectId}/plans`, form, { headers: { 'Content-Type': 'multipart/form-data' } })
    .then((response) => response.data)
}

export function planPagePreviewUrl(projectId, planId, pageNumber) {
  const base = api.defaults.baseURL || ''
  return `${base}/api/projects/${projectId}/plans/${planId}/pages/${pageNumber}/preview`
}

// -- Legend entries ----------------------------------------------------

function legendBase(projectId, planId) {
  return `/api/projects/${projectId}/plans/${planId}/legend-entries`
}

export function createLegendEntry(projectId, planId, pageNumber) {
  return api.post(legendBase(projectId, planId), { page_number: pageNumber }).then((response) => response.data)
}

export function listLegendEntries(projectId, planId) {
  return api.get(legendBase(projectId, planId)).then((response) => response.data)
}

export function getLegendEntry(projectId, planId, legendEntryId) {
  return api.get(`${legendBase(projectId, planId)}/${legendEntryId}`).then((response) => response.data)
}

export function updateLegendEntry(projectId, planId, legendEntryId, patch) {
  return api.patch(`${legendBase(projectId, planId)}/${legendEntryId}`, patch).then((response) => response.data)
}

export function savePatternSelection(projectId, planId, legendEntryId, normalizedRect) {
  return api
    .post(`${legendBase(projectId, planId)}/${legendEntryId}/pattern`, normalizedRect)
    .then((response) => response.data)
}

export function saveDescriptionSelection(projectId, planId, legendEntryId, normalizedRect) {
  return api
    .post(`${legendBase(projectId, planId)}/${legendEntryId}/description`, normalizedRect)
    .then((response) => response.data)
}

export function runOcr(projectId, planId, legendEntryId) {
  return api.post(`${legendBase(projectId, planId)}/${legendEntryId}/ocr`).then((response) => response.data)
}

export function confirmLegendEntry(projectId, planId, legendEntryId) {
  return api.post(`${legendBase(projectId, planId)}/${legendEntryId}/confirm`).then((response) => response.data)
}

// -- Hatch features (R4) -- thin, optional: getHatchFeatures returning
// null on 404 is the normal "not computed yet" case, not an error.

function featuresBase(projectId, planId, legendEntryId) {
  return `${legendBase(projectId, planId)}/${legendEntryId}/features`
}

export function computeHatchFeatures(projectId, planId, legendEntryId, force = false) {
  return api.post(featuresBase(projectId, planId, legendEntryId), { force }).then((response) => response.data)
}

export function getHatchFeatures(projectId, planId, legendEntryId) {
  return api
    .get(featuresBase(projectId, planId, legendEntryId))
    .then((response) => response.data)
    .catch((err) => {
      if (err?.response?.status === 404) return null
      throw err
    })
}

// -- Pattern library (R5) -----------------------------------------------

export function addToPatternLibrary(projectId, planId, legendEntryId) {
  return api.post(`${legendBase(projectId, planId)}/${legendEntryId}/library`).then((response) => response.data)
}

export function listPatternLibrary(projectId) {
  return api.get(`/api/projects/${projectId}/pattern-library`).then((response) => response.data)
}

export function computeMatches(projectId, planId, legendEntryId, topK) {
  return api
    .post(`${legendBase(projectId, planId)}/${legendEntryId}/matches`, topK ? { top_k: topK } : {})
    .then((response) => response.data)
}

export function recordMatchDecision(projectId, planId, legendEntryId, payload) {
  return api
    .post(`${legendBase(projectId, planId)}/${legendEntryId}/match-decision`, payload)
    .then((response) => response.data)
}

export function listMatchDecisions(projectId, planId, legendEntryId) {
  return api.get(`${legendBase(projectId, planId)}/${legendEntryId}/match-decisions`).then((response) => response.data)
}

// -- Detection Engine V2 (R6) --------------------------------------------

export function startDetectionRun(projectId, planId, pageNumber, referenceLegendEntryId) {
  return api
    .post(`/api/projects/${projectId}/plans/${planId}/pages/${pageNumber}/detection-runs`, {
      legend_entry_id: referenceLegendEntryId,
    })
    .then((response) => response.data)
}

export function listDetectionRunsForPage(projectId, planId, pageNumber) {
  return api
    .get(`/api/projects/${projectId}/plans/${planId}/pages/${pageNumber}/detection-runs`)
    .then((response) => response.data)
}

export function getDetectionRun(projectId, planId, runId) {
  return api.get(`/api/projects/${projectId}/plans/${planId}/detection-runs/${runId}`).then((response) => response.data)
}

export function listDetectedRegions(projectId, planId, runId) {
  return api
    .get(`/api/projects/${projectId}/plans/${planId}/detection-runs/${runId}/regions`)
    .then((response) => response.data)
}

export function updateDetectedRegion(projectId, planId, runId, regionId, status) {
  return api
    .patch(`/api/projects/${projectId}/plans/${planId}/detection-runs/${runId}/regions/${regionId}`, { status })
    .then((response) => response.data)
}

// -- R7: manual corrections, plan scale, quantity ------------------------

function runBase(projectId, planId, runId) {
  return `/api/projects/${projectId}/plans/${planId}/detection-runs/${runId}`
}

export function createManualCorrection(projectId, planId, runId, correctionType, normalizedRect) {
  return api
    .post(`${runBase(projectId, planId, runId)}/manual-corrections`, {
      correction_type: correctionType,
      x: normalizedRect.x,
      y: normalizedRect.y,
      width: normalizedRect.width,
      height: normalizedRect.height,
    })
    .then((response) => response.data)
}

export function listManualCorrections(projectId, planId, runId) {
  return api.get(`${runBase(projectId, planId, runId)}/manual-corrections`).then((response) => response.data)
}

export function deleteManualCorrection(projectId, planId, runId, correctionId) {
  return api.delete(`${runBase(projectId, planId, runId)}/manual-corrections/${correctionId}`)
}

export function getPlanScale(projectId, planId, pageNumber) {
  return api
    .get(`/api/projects/${projectId}/plans/${planId}/pages/${pageNumber}/scale`)
    .then((response) => response.data)
    .catch((err) => {
      if (err?.response?.status === 404) return null
      throw err
    })
}

export function confirmDeclaredScale(projectId, planId, pageNumber, declaredRatio) {
  return api
    .put(`/api/projects/${projectId}/plans/${planId}/pages/${pageNumber}/scale`, {
      method: 'declared_scale',
      declared_ratio: declaredRatio,
    })
    .then((response) => response.data)
}

export function confirmCalibratedScale(projectId, planId, pageNumber, planPoints, realMeters) {
  return api
    .put(`/api/projects/${projectId}/plans/${planId}/pages/${pageNumber}/scale`, {
      method: 'calibrated_distance',
      calibrated_distance_plan_points: planPoints,
      calibrated_distance_real_m: realMeters,
    })
    .then((response) => response.data)
}

export function calculateQuantity(projectId, planId, runId, confirmedDimensionM) {
  return api
    .post(`${runBase(projectId, planId, runId)}/quantity`, { confirmed_dimension_m: confirmedDimensionM })
    .then((response) => response.data)
}

export function getQuantity(projectId, planId, runId) {
  return api
    .get(`${runBase(projectId, planId, runId)}/quantity`)
    .then((response) => response.data)
    .catch((err) => {
      if (err?.response?.status === 404) return null
      throw err
    })
}

export function confirmQuantity(projectId, planId, runId) {
  return api.post(`${runBase(projectId, planId, runId)}/quantity/confirm`).then((response) => response.data)
}

// -- Results & Export (R8) ------------------------------------------------

export function listResults(projectId) {
  return api.get(`/api/projects/${projectId}/results`).then((response) => response.data)
}

export function getResult(projectId, quantityResultId) {
  return api.get(`/api/projects/${projectId}/results/${quantityResultId}`).then((response) => response.data)
}

export function exportPreflight(projectId) {
  return api.get(`/api/projects/${projectId}/results/export/preflight`).then((response) => response.data)
}

/** Downloads the authoritative CONFIRMED-only Excel workbook. Returns the
 * response so the caller can drive a real browser download from a real
 * blob -- this function never constructs workbook bytes itself, it only
 * triggers the backend to generate them (R8 section 25). */
export function exportResults(projectId) {
  return api.post(`/api/projects/${projectId}/results/export`, null, { responseType: 'blob' })
}

export function patternCropUrl(projectId, planId, legendEntryId, cacheBust) {
  const base = api.defaults.baseURL || ''
  return `${base}${legendBase(projectId, planId)}/${legendEntryId}/pattern?v=${cacheBust || 0}`
}

export function descriptionCropUrl(projectId, planId, legendEntryId, cacheBust) {
  const base = api.defaults.baseURL || ''
  return `${base}${legendBase(projectId, planId)}/${legendEntryId}/description?v=${cacheBust || 0}`
}
