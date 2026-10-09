import { useCallback, useEffect, useState } from 'react'

const PARAM_KEYS = { projectId: 'project', planId: 'plan', pageNumber: 'page', stage: 'stage' }

function readParams() {
  const params = new URLSearchParams(window.location.search)
  return {
    projectId: params.get(PARAM_KEYS.projectId) || '',
    planId: params.get(PARAM_KEYS.planId) || '',
    pageNumber: params.get(PARAM_KEYS.pageNumber) ? Number(params.get(PARAM_KEYS.pageNumber)) : null,
    stage: params.get(PARAM_KEYS.stage) || '',
  }
}

function writeParams(next) {
  const params = new URLSearchParams(window.location.search)
  Object.entries(next).forEach(([key, value]) => {
    const paramKey = PARAM_KEYS[key]
    if (!paramKey) return
    if (value === null || value === undefined || value === '') {
      params.delete(paramKey)
    } else {
      params.set(paramKey, String(value))
    }
  })
  const query = params.toString()
  const url = `${window.location.pathname}${query ? `?${query}` : ''}`
  window.history.replaceState(null, '', url)
}

/**
 * R9 section 30's minimum bar: preserve project identity and safely
 * restore the relevant workflow state on refresh, without introducing a
 * router library (there is none in this app today, and a full migration
 * is unjustified churn for a single-page app). Plain URLSearchParams +
 * history.replaceState, restored on mount and on browser back/forward.
 */
export function useWorkflowUrlState() {
  const [state, setStateRaw] = useState(readParams)

  useEffect(() => {
    const onPopState = () => setStateRaw(readParams())
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const setState = useCallback((patch) => {
    setStateRaw((prev) => {
      const next = { ...prev, ...patch }
      writeParams(next)
      return next
    })
  }, [])

  return [state, setState]
}
