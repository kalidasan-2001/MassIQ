/**
 * Shared HTTPException.detail parsing for the persisted-project workflow.
 * The backend sometimes returns a plain string, sometimes a structured
 * object (`{ message, reasons: [...] }` for validation errors, or
 * `{ error_code, message, ... }` for domain errors like
 * REFERENCE_FEATURE_VERSION_OUTDATED -- see routes/detection_runs.py).
 * Centralized here so every caller renders a human string consistently
 * instead of accidentally dumping "[object Object]" into the UI.
 */
export function extractErrorMessage(err, fallback) {
  const detail = err?.response?.data?.detail
  if (detail && typeof detail === 'object') {
    if (Array.isArray(detail.reasons)) return `${detail.message}: ${detail.reasons.join(', ')}`
    if (typeof detail.message === 'string') return detail.message
  }
  return detail || err?.message || fallback
}

/** Returns the backend's `error_code` for a structured domain error, or
 * undefined for plain-string/validation errors -- lets callers special-case
 * a specific, known, actionable error (e.g. show a "recompute features"
 * link) without string-matching the message text. */
export function extractErrorCode(err) {
  const detail = err?.response?.data?.detail
  return detail && typeof detail === 'object' ? detail.error_code : undefined
}
