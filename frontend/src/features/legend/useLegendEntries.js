import { useCallback, useState } from 'react'
import * as legendApi from './api'

/**
 * Wraps the legend-entries API + local list state for one (projectId,
 * planId) pair. Mutating actions (savePattern/saveDescription/runOcr/
 * updateEntry/confirmEntry) update the local list on success and otherwise
 * let the caller catch/display the error -- matching the existing
 * per-panel loading/error convention already used by
 * HatchDetectionPanel.jsx/LegendAssistantPanel.jsx, rather than
 * centralizing UI feedback state here too.
 */
export function useLegendEntries(projectId, planId) {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    if (!projectId || !planId) return
    setLoading(true)
    setError('')
    try {
      const data = await legendApi.listLegendEntries(projectId, planId)
      setEntries(data)
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Failed to load legend entries')
    } finally {
      setLoading(false)
    }
  }, [projectId, planId])

  const applyUpdate = (updated) => {
    setEntries((prev) => (prev.some((entry) => entry.id === updated.id) ? prev.map((entry) => (entry.id === updated.id ? updated : entry)) : [updated, ...prev]))
  }

  const createDraft = useCallback(
    async (pageNumber) => {
      const entry = await legendApi.createLegendEntry(projectId, planId, pageNumber)
      applyUpdate(entry)
      return entry
    },
    [projectId, planId]
  )

  const savePattern = useCallback(
    async (entryId, normalizedRect) => {
      const updated = await legendApi.savePatternSelection(projectId, planId, entryId, normalizedRect)
      applyUpdate(updated)
      return updated
    },
    [projectId, planId]
  )

  const saveDescription = useCallback(
    async (entryId, normalizedRect) => {
      const updated = await legendApi.saveDescriptionSelection(projectId, planId, entryId, normalizedRect)
      applyUpdate(updated)
      return updated
    },
    [projectId, planId]
  )

  const runOcr = useCallback(
    async (entryId) => {
      const updated = await legendApi.runOcr(projectId, planId, entryId)
      applyUpdate(updated)
      return updated
    },
    [projectId, planId]
  )

  const updateEntry = useCallback(
    async (entryId, patch) => {
      const updated = await legendApi.updateLegendEntry(projectId, planId, entryId, patch)
      applyUpdate(updated)
      return updated
    },
    [projectId, planId]
  )

  const confirmEntry = useCallback(
    async (entryId) => {
      const updated = await legendApi.confirmLegendEntry(projectId, planId, entryId)
      applyUpdate(updated)
      return updated
    },
    [projectId, planId]
  )

  return {
    entries,
    loading,
    error,
    refresh,
    createDraft,
    savePattern,
    saveDescription,
    runOcr,
    updateEntry,
    confirmEntry,
  }
}
