import { useEffect, useMemo, useState } from 'react'
import { usePageSelection } from '../legend/usePageSelection'
import { useLegendEntries } from '../legend/useLegendEntries'
import { extractErrorMessage, extractErrorCode } from '../legend/apiErrors'
import * as legendApi from '../legend/api'
import { deriveWorkflowStages, pickCurrentStage, isEntryInLibrary } from './deriveWorkflowStages'

/**
 * R9: the single source of truth for one (projectId, planId, pageNumber)
 * workflow session. This is the old LegendWorkspace.jsx's state/effects/
 * handlers, lifted one level so the new stage components
 * (features/workflow/*Stage.jsx) can each render a thin slice of it
 * instead of one 623-line component owning every stage's UI. No behavior
 * changed here versus the pre-R9 flow -- same API calls, same effects,
 * same handlers -- only reorganized, plus the derived `stages` status and
 * the `inLibrary` staleness fix (R9 audit finding: it used to be a
 * session-only flag that forgot "already in library" across a refresh;
 * now it's derived from the fetched library list every time).
 */
export function useProjectWorkflowState({ projectId, planId, pageNumber, planPageId, plans, onLibraryChanged, onResultsChanged }) {
  const [activeEntryId, setActiveEntryId] = useState(null)
  const [creating, setCreating] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [cropVersion, setCropVersion] = useState(0)
  const [hatchFeatures, setHatchFeatures] = useState(null)
  const [featuresBusy, setFeaturesBusy] = useState(false)
  const [libraryEntries, setLibraryEntries] = useState([])
  const [libraryBusy, setLibraryBusy] = useState(false)
  const [detectionRun, setDetectionRun] = useState(null)
  const [detectedRegions, setDetectedRegions] = useState([])
  const [detectionBusy, setDetectionBusy] = useState(false)
  const [featureVersionOutdated, setFeatureVersionOutdated] = useState(false)
  const [manualCorrections, setManualCorrections] = useState([])
  const [planScale, setPlanScale] = useState(null)
  const [quantityResult, setQuantityResult] = useState(null)
  const [quantityBusy, setQuantityBusy] = useState(false)

  const {
    entries,
    loading: entriesLoading,
    error: entriesError,
    refresh: refreshEntries,
    createDraft,
    savePattern,
    saveDescription,
    runOcr,
    updateEntry,
    confirmEntry,
  } = useLegendEntries(projectId, planId)

  useEffect(() => {
    refreshEntries()
  }, [refreshEntries])

  const pageEntries = useMemo(
    () => (planPageId ? entries.filter((entry) => entry.plan_page_id === planPageId) : entries),
    [entries, planPageId]
  )
  const activeEntry = pageEntries.find((entry) => entry.id === activeEntryId) || null

  // Best-effort status lookup only -- a 404 (not yet computed) is the
  // normal case, not an error condition, and this never triggers
  // computation itself (see legendApi.getHatchFeatures).
  useEffect(() => {
    let cancelled = false
    setHatchFeatures(null)
    if (activeEntry?.status === 'confirmed') {
      legendApi.getHatchFeatures(projectId, planId, activeEntry.id).then((result) => {
        if (!cancelled) setHatchFeatures(result)
      })
    }
    return () => {
      cancelled = true
    }
  }, [projectId, planId, activeEntry?.id, activeEntry?.status])

  const refreshLibrary = () => {
    if (!projectId) return
    legendApi
      .listPatternLibrary(projectId)
      .then((result) => setLibraryEntries(result))
      .catch(() => {})
  }

  useEffect(refreshLibrary, [projectId])

  // R9 audit fix: "already in library" is derived from the fetched
  // library list (matched on source_legend_entry_id), not a session-only
  // flag -- so it survives a refresh instead of forgetting a pattern was
  // already added until the user clicks "Add" again.
  const inLibrary = isEntryInLibrary(activeEntry, libraryEntries)

  // Rediscovers the most recent Detection V2 run for this page after a
  // mount/reload -- the DB is the only source of truth, nothing is cached
  // client-side.
  useEffect(() => {
    let cancelled = false
    setDetectionRun(null)
    setDetectedRegions([])
    if (!projectId || !planId) return undefined
    legendApi
      .listDetectionRunsForPage(projectId, planId, pageNumber)
      .then((runs) => {
        if (cancelled || runs.length === 0) return
        const mostRecent = runs[0]
        setDetectionRun(mostRecent)
        if (mostRecent.status === 'completed') {
          legendApi.listDetectedRegions(projectId, planId, mostRecent.id).then((regions) => {
            if (!cancelled) setDetectedRegions(regions)
          })
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [projectId, planId, pageNumber])

  // PlanScale is page-scoped (reused by every run on this page), so it is
  // rediscovered independently of any particular DetectionRun.
  useEffect(() => {
    let cancelled = false
    setPlanScale(null)
    if (!projectId || !planId) return undefined
    legendApi
      .getPlanScale(projectId, planId, pageNumber)
      .then((scale) => {
        if (!cancelled) setPlanScale(scale)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [projectId, planId, pageNumber])

  // Manual corrections and the QuantityResult are scoped to the
  // rediscovered DetectionRun -- re-fetched whenever that run identity
  // changes, including right after it is first rediscovered on a fresh
  // reload.
  useEffect(() => {
    let cancelled = false
    setManualCorrections([])
    setQuantityResult(null)
    if (!detectionRun) return undefined
    legendApi
      .listManualCorrections(projectId, planId, detectionRun.id)
      .then((corrections) => {
        if (!cancelled) setManualCorrections(corrections)
      })
      .catch(() => {})
    legendApi
      .getQuantity(projectId, planId, detectionRun.id)
      .then((result) => {
        if (!cancelled) setQuantityResult(result)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [projectId, planId, detectionRun?.id])

  const handleRegionComplete = async (mode, normalizedRect) => {
    if (mode === 'manual_add' || mode === 'manual_subtract') {
      if (!detectionRun) {
        setActionError('Run Detection V2 before adding manual corrections.')
        return
      }
      setQuantityBusy(true)
      setActionError('')
      try {
        const correctionType = mode === 'manual_add' ? 'add' : 'subtract'
        const created = await legendApi.createManualCorrection(
          projectId, planId, detectionRun.id, correctionType, normalizedRect
        )
        setManualCorrections((prev) => [...prev, created])
      } catch (err) {
        setActionError(extractErrorMessage(err, 'Failed to save the manual correction.'))
      } finally {
        setQuantityBusy(false)
      }
      return
    }

    if (!activeEntryId) {
      setActionError('Create or select a legend entry before drawing a selection.')
      return
    }
    setActionBusy(true)
    setActionError('')
    try {
      if (mode === 'pattern') {
        await savePattern(activeEntryId, normalizedRect)
      } else {
        await saveDescription(activeEntryId, normalizedRect)
      }
      setCropVersion((value) => value + 1)
    } catch (err) {
      setActionError(extractErrorMessage(err, 'Failed to save selection.'))
    } finally {
      setActionBusy(false)
    }
  }

  const selection = usePageSelection(handleRegionComplete)

  const handleCreateNew = async () => {
    setCreating(true)
    setActionError('')
    try {
      const entry = await createDraft(pageNumber)
      setActiveEntryId(entry.id)
    } catch (err) {
      setActionError(extractErrorMessage(err, 'Failed to create legend entry.'))
    } finally {
      setCreating(false)
    }
  }

  const handleRunOcr = async () => {
    if (!activeEntryId) return
    setActionBusy(true)
    setActionError('')
    try {
      await runOcr(activeEntryId)
    } catch (err) {
      // OCR failure is non-fatal by design -- the user can still type the
      // description manually, so this is shown as a recoverable notice,
      // not a blocking error.
      setActionError(extractErrorMessage(err, 'OCR failed -- you can still type the description manually below.'))
    } finally {
      setActionBusy(false)
    }
  }

  const handleSaveCorrection = async (patch) => {
    if (!activeEntryId) return
    setActionBusy(true)
    setActionError('')
    try {
      await updateEntry(activeEntryId, patch)
    } catch (err) {
      setActionError(extractErrorMessage(err, 'Failed to save correction.'))
    } finally {
      setActionBusy(false)
    }
  }

  const handleConfirm = async () => {
    if (!activeEntryId) return
    setActionBusy(true)
    setActionError('')
    try {
      await confirmEntry(activeEntryId)
    } catch (err) {
      setActionError(extractErrorMessage(err, 'Cannot confirm this legend entry yet.'))
    } finally {
      setActionBusy(false)
    }
  }

  const handleComputeFeatures = async () => {
    if (!activeEntryId) return
    setFeaturesBusy(true)
    setActionError('')
    try {
      const result = await legendApi.computeHatchFeatures(projectId, planId, activeEntryId, !!hatchFeatures)
      setHatchFeatures(result)
    } catch (err) {
      setActionError(extractErrorMessage(err, 'Failed to compute hatch features.'))
    } finally {
      setFeaturesBusy(false)
    }
  }

  const handleAddToLibrary = async () => {
    if (!activeEntryId) return
    setLibraryBusy(true)
    setActionError('')
    try {
      await legendApi.addToPatternLibrary(projectId, planId, activeEntryId)
      refreshLibrary()
      onLibraryChanged?.()
    } catch (err) {
      setActionError(extractErrorMessage(err, 'Failed to add this pattern to the project library.'))
    } finally {
      setLibraryBusy(false)
    }
  }

  const handleRunDetection = async () => {
    if (!activeEntryId) return
    setDetectionBusy(true)
    setActionError('')
    setFeatureVersionOutdated(false)
    try {
      const run = await legendApi.startDetectionRun(projectId, planId, pageNumber, activeEntryId)
      setDetectionRun(run)
      if (run.status === 'completed') {
        const regions = await legendApi.listDetectedRegions(projectId, planId, run.id)
        setDetectedRegions(regions)
      } else {
        setDetectedRegions([])
      }
    } catch (err) {
      setActionError(extractErrorMessage(err, 'Detection V2 failed to run.'))
      setFeatureVersionOutdated(extractErrorCode(err) === 'REFERENCE_FEATURE_VERSION_OUTDATED')
    } finally {
      setDetectionBusy(false)
    }
  }

  const handleUpdateRegionStatus = async (regionId, status) => {
    if (!detectionRun) return
    setDetectionBusy(true)
    setActionError('')
    try {
      const updated = await legendApi.updateDetectedRegion(projectId, planId, detectionRun.id, regionId, status)
      setDetectedRegions((prev) => prev.map((region) => (region.id === regionId ? updated : region)))
    } catch (err) {
      setActionError(extractErrorMessage(err, 'Failed to update the region.'))
    } finally {
      setDetectionBusy(false)
    }
  }

  const handleDeleteManualCorrection = async (correctionId) => {
    if (!detectionRun) return
    setQuantityBusy(true)
    setActionError('')
    try {
      await legendApi.deleteManualCorrection(projectId, planId, detectionRun.id, correctionId)
      setManualCorrections((prev) => prev.filter((c) => c.id !== correctionId))
    } catch (err) {
      setActionError(extractErrorMessage(err, 'Failed to remove the manual correction.'))
    } finally {
      setQuantityBusy(false)
    }
  }

  const handleConfirmDeclaredScale = async (declaredRatio) => {
    setQuantityBusy(true)
    setActionError('')
    try {
      const scale = await legendApi.confirmDeclaredScale(projectId, planId, pageNumber, declaredRatio)
      setPlanScale(scale)
    } catch (err) {
      setActionError(extractErrorMessage(err, 'Failed to confirm scale.'))
    } finally {
      setQuantityBusy(false)
    }
  }

  const handleConfirmCalibratedScale = async (planPoints, realMeters) => {
    setQuantityBusy(true)
    setActionError('')
    try {
      const scale = await legendApi.confirmCalibratedScale(projectId, planId, pageNumber, planPoints, realMeters)
      setPlanScale(scale)
    } catch (err) {
      setActionError(extractErrorMessage(err, 'Failed to confirm scale.'))
    } finally {
      setQuantityBusy(false)
    }
  }

  const handleCalculateQuantity = async (confirmedDimensionM) => {
    if (!detectionRun) return
    setQuantityBusy(true)
    setActionError('')
    try {
      const result = await legendApi.calculateQuantity(projectId, planId, detectionRun.id, confirmedDimensionM)
      setQuantityResult(result)
      onResultsChanged?.()
    } catch (err) {
      setActionError(extractErrorMessage(err, 'Failed to calculate quantity.'))
    } finally {
      setQuantityBusy(false)
    }
  }

  const handleConfirmQuantityResult = async () => {
    if (!detectionRun) return
    setQuantityBusy(true)
    setActionError('')
    try {
      const result = await legendApi.confirmQuantity(projectId, planId, detectionRun.id)
      setQuantityResult(result)
      onResultsChanged?.()
    } catch (err) {
      setActionError(extractErrorMessage(err, 'Failed to confirm quantity result.'))
    } finally {
      setQuantityBusy(false)
    }
  }

  const reviewCounts = {
    candidate: detectedRegions.filter((r) => r.status === 'candidate').length,
    accepted: detectedRegions.filter((r) => r.status === 'accepted').length,
    rejected: detectedRegions.filter((r) => r.status === 'rejected').length,
    manualAdd: manualCorrections.filter((c) => c.correction_type === 'add').length,
    manualSubtract: manualCorrections.filter((c) => c.correction_type === 'subtract').length,
  }

  const overlays = [
    activeEntry?.has_pattern_selection
      ? {
          kind: 'pattern',
          rect: {
            x: activeEntry.pattern_x,
            y: activeEntry.pattern_y,
            width: activeEntry.pattern_width,
            height: activeEntry.pattern_height,
          },
        }
      : null,
    activeEntry?.has_description_selection
      ? {
          kind: 'description',
          rect: {
            x: activeEntry.description_x,
            y: activeEntry.description_y,
            width: activeEntry.description_width,
            height: activeEntry.description_height,
          },
        }
      : null,
  ].filter(Boolean)

  const stages = deriveWorkflowStages({
    hasProject: !!projectId,
    plans,
    hasPlanSelected: !!planId && !!pageNumber,
    planScale,
    pageLegendEntries: pageEntries,
    activeEntryConfirmed: activeEntry?.status === 'confirmed',
    hatchFeatures,
    libraryEntries,
    detectionRun,
    detectedRegions,
    quantityResult,
  })
  const currentStage = pickCurrentStage(stages)

  return {
    // legend entries
    entries: pageEntries,
    entriesLoading,
    entriesError,
    activeEntryId,
    setActiveEntryId,
    activeEntry,
    creating,
    handleCreateNew,

    // legend entry editing
    cropVersion,
    actionBusy,
    actionError,
    handleRunOcr,
    handleSaveCorrection,
    handleConfirm,

    // hatch features / library
    hatchFeatures,
    featuresBusy,
    handleComputeFeatures,
    libraryEntries,
    inLibrary,
    libraryBusy,
    handleAddToLibrary,

    // detection / review
    detectionRun,
    detectedRegions,
    detectionBusy,
    featureVersionOutdated,
    handleRunDetection,
    handleUpdateRegionStatus,

    // manual corrections
    manualCorrections,
    handleDeleteManualCorrection,

    // scale / quantity
    planScale,
    quantityResult,
    quantityBusy,
    handleConfirmDeclaredScale,
    handleConfirmCalibratedScale,
    handleCalculateQuantity,
    handleConfirmQuantityResult,

    // shared canvas
    selection,
    overlays,
    reviewCounts,

    // derived workflow status
    stages,
    currentStage,
  }
}
