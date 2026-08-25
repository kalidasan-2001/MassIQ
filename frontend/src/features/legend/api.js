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

export function patternCropUrl(projectId, planId, legendEntryId, cacheBust) {
  const base = api.defaults.baseURL || ''
  return `${base}${legendBase(projectId, planId)}/${legendEntryId}/pattern?v=${cacheBust || 0}`
}

export function descriptionCropUrl(projectId, planId, legendEntryId, cacheBust) {
  const base = api.defaults.baseURL || ''
  return `${base}${legendBase(projectId, planId)}/${legendEntryId}/description?v=${cacheBust || 0}`
}
