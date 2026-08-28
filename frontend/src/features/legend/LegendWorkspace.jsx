import React, { useEffect, useMemo, useState } from 'react'
import { normalizedToDisplayRect } from './coordinates'
import { usePageSelection } from './usePageSelection'
import { useLegendEntries } from './useLegendEntries'
import LegendSelectionToolbar from './LegendSelectionToolbar'
import LegendEntryEditor from './LegendEntryEditor'
import LegendEntryList from './LegendEntryList'
import DetectionPanel from './DetectionPanel'
import ManualCorrectionPanel from './ManualCorrectionPanel'
import QuantityPanel from './QuantityPanel'
import * as legendApi from './api'

const MODE_LABELS = {
  pattern: 'pattern selection',
  description: 'description selection',
  manual_add: 'manual Add region',
  manual_subtract: 'manual Subtract region',
}

function extractErrorMessage(err, fallback) {
  const detail = err?.response?.data?.detail
  if (detail && typeof detail === 'object' && Array.isArray(detail.reasons)) {
    return `${detail.message}: ${detail.reasons.join(', ')}`
  }
  return detail || err?.message || fallback
}

/**
 * Composes the persisted-plan-page view, the two-selection toolbar, the
 * OCR/correction/material editor, and the entry list for one
 * (projectId, planId, pageNumber). This is the top of the R3 feature --
 * PlanViewer.jsx is not touched by any of this.
 */
export default function LegendWorkspace({ projectId, planId, pageNumber, planPageId, previewUrl, onLibraryChanged }) {
  const [activeEntryId, setActiveEntryId] = useState(null)
  const [creating, setCreating] = useState(false)
  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [cropVersion, setCropVersion] = useState(0)
  const [hatchFeatures, setHatchFeatures] = useState(null)
  const [featuresBusy, setFeaturesBusy] = useState(false)
  const [inLibrary, setInLibrary] = useState(false)
  const [libraryBusy, setLibraryBusy] = useState(false)
  const [detectionRun, setDetectionRun] = useState(null)
  const [detectedRegions, setDetectedRegions] = useState([])
  const [detectionBusy, setDetectionBusy] = useState(false)
  const [manualCorrections, setManualCorrections] = useState([])
  const [planScale, setPlanScale] = useState(null)
  const [quantityResult, setQuantityResult] = useState(null)
  const [quantityBusy, setQuantityBusy] = useState(false)

  const {
    entries,
    loading,
    error: listError,
    refresh,
    createDraft,
    savePattern,
    saveDescription,
    runOcr,
    updateEntry,
    confirmEntry,
  } = useLegendEntries(projectId, planId)

  useEffect(() => {
    refresh()
  }, [refresh])

  const pageEntries = useMemo(
    () => (planPageId ? entries.filter((entry) => entry.plan_page_id === planPageId) : entries),
    [entries, planPageId]
  )
  const activeEntry = pageEntries.find((entry) => entry.id === activeEntryId) || null

  // R4: best-effort status lookup only -- a 404 (not yet computed) is the
  // normal case, not an error condition, and this never triggers
  // computation itself (see legendApi.getHatchFeatures).
  useEffect(() => {
    let cancelled = false
    setHatchFeatures(null)
    setInLibrary(false)
    if (activeEntry?.status === 'confirmed') {
      legendApi.getHatchFeatures(projectId, planId, activeEntry.id).then((result) => {
        if (!cancelled) setHatchFeatures(result)
      })
    }
    return () => {
      cancelled = true
    }
  }, [projectId, planId, activeEntry?.id, activeEntry?.status])

  // R6: rediscovers the most recent Detection V2 run for this page after
  // a mount/reload -- the DB is the only source of truth (see
  // DetectionService.list_runs_for_page), nothing is cached client-side.
  useEffect(() => {
    let cancelled = false
    setDetectionRun(null)
    setDetectedRegions([])
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

  // R7: PlanScale is page-scoped (reused by every run on this page), so
  // it is rediscovered independently of any particular DetectionRun.
  // Same "DB is the only source of truth, .catch swallows the normal
  // not-yet-confirmed 404" discipline as the R6 run-rediscovery effect
  // above.
  useEffect(() => {
    let cancelled = false
    setPlanScale(null)
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

  // R7: manual corrections and the QuantityResult are scoped to the
  // rediscovered DetectionRun (see the effect above) -- re-fetched
  // whenever that run identity changes, including right after it is
  // first rediscovered on a fresh reload.
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
      setInLibrary(true)
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

  const draftDisplayRect = selection.draftRect
    ? {
        left: Math.min(selection.draftRect.startX, selection.draftRect.endX),
        top: Math.min(selection.draftRect.startY, selection.draftRect.endY),
        width: Math.abs(selection.draftRect.endX - selection.draftRect.startX),
        height: Math.abs(selection.draftRect.endY - selection.draftRect.startY),
      }
    : null

  return (
    <div className="two-col">
      <div className="card panel">
        <strong>Plan Page {pageNumber}</strong>
        <p className="muted">
          {selection.mode
            ? `Drawing ${MODE_LABELS[selection.mode] || selection.mode} -- drag a rectangle on the page.`
            : 'Create or select a legend entry, then draw a pattern and description selection.'}
        </p>
        <div
          className="plan-stage"
          onMouseDown={selection.onMouseDown}
          onMouseMove={selection.onMouseMove}
          onMouseUp={selection.onMouseUp}
          onMouseLeave={selection.onMouseUp}
          ref={selection.containerRef}
        >
          {/* draggable={false} is load-bearing, not cosmetic: <img> is
              natively draggable by default, and mousedown-then-move on an
              undraggable-unset image makes Chromium hijack the gesture into
              a native OS-level image drag after the first mousemove --
              silently swallowing every mousemove/mouseup our own selection
              handlers need. Found via real Playwright browser testing (a
              curl-only check of the API can never catch this class of bug). */}
          <img
            alt={`Plan page ${pageNumber}`}
            className="plan-image"
            src={previewUrl}
            onLoad={selection.onImageLoad}
            draggable={false}
          />
          {overlays.map((overlay) => {
            const display = normalizedToDisplayRect(overlay.rect, selection.viewSize)
            if (!display) return null
            return (
              <div
                key={overlay.kind}
                className={`plan-overlay overlay-${overlay.kind}`}
                style={{ left: display.left, top: display.top, width: display.width, height: display.height }}
              />
            )
          })}
          {detectedRegions.map((region) => {
            const display = normalizedToDisplayRect(region, selection.viewSize)
            if (!display) return null
            return (
              <div
                key={region.id}
                className={`plan-overlay overlay-detection-${region.status}`}
                style={{ left: display.left, top: display.top, width: display.width, height: display.height }}
              />
            )
          })}
          {manualCorrections.map((correction) => {
            const display = normalizedToDisplayRect(correction, selection.viewSize)
            if (!display) return null
            return (
              <div
                key={correction.id}
                className={`plan-overlay overlay-${correction.correction_type}`}
                style={{ left: display.left, top: display.top, width: display.width, height: display.height }}
                data-testid={`manual-overlay-${correction.correction_type}`}
              />
            )
          })}
          {draftDisplayRect && (
            <div
              className="plan-overlay overlay-draft"
              style={{
                left: draftDisplayRect.left,
                top: draftDisplayRect.top,
                width: draftDisplayRect.width,
                height: draftDisplayRect.height,
              }}
            />
          )}
        </div>
        <div style={{ marginTop: 12 }}>
          <LegendSelectionToolbar
            mode={selection.mode}
            disabled={!activeEntryId || actionBusy}
            onStartPattern={() => selection.startMode('pattern')}
            onStartDescription={() => selection.startMode('description')}
            onCancel={selection.cancelMode}
          />
        </div>
        {!activeEntryId && (
          <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
            Create or select a legend entry (right) to enable drawing a selection here.
          </p>
        )}
      </div>

      <div>
        <LegendEntryList
          entries={pageEntries}
          activeEntryId={activeEntryId}
          onSelect={setActiveEntryId}
          onCreateNew={handleCreateNew}
          creating={creating}
        />
        {loading && <p className="muted">Loading legend entries...</p>}
        {listError && <p className="error">{listError}</p>}
        <div style={{ marginTop: 16 }}>
          <LegendEntryEditor
            entry={activeEntry}
            patternCropSrc={
              activeEntry?.has_pattern_selection
                ? legendApi.patternCropUrl(projectId, planId, activeEntry.id, cropVersion)
                : null
            }
            descriptionCropSrc={
              activeEntry?.has_description_selection
                ? legendApi.descriptionCropUrl(projectId, planId, activeEntry.id, cropVersion)
                : null
            }
            busy={actionBusy}
            error={actionError}
            onRunOcr={handleRunOcr}
            onSaveCorrection={handleSaveCorrection}
            onConfirm={handleConfirm}
            hatchFeatures={hatchFeatures}
            featuresBusy={featuresBusy}
            onComputeFeatures={handleComputeFeatures}
            projectId={projectId}
            planId={planId}
            inLibrary={inLibrary}
            libraryBusy={libraryBusy}
            onAddToLibrary={handleAddToLibrary}
          />
        </div>

        {hatchFeatures && (
          <div className="card panel" style={{ marginTop: 16 }}>
            <DetectionPanel
              run={detectionRun}
              regions={detectedRegions}
              busy={detectionBusy}
              disabled={!activeEntryId}
              onRunDetection={handleRunDetection}
              onUpdateRegionStatus={handleUpdateRegionStatus}
            />
          </div>
        )}

        {detectionRun && detectionRun.status === 'completed' && (
          <div className="card panel" style={{ marginTop: 16 }}>
            <ManualCorrectionPanel
              mode={selection.mode === 'manual_add' || selection.mode === 'manual_subtract' ? selection.mode : null}
              corrections={manualCorrections}
              busy={quantityBusy}
              disabled={actionBusy}
              onStartAdd={() => selection.startMode('manual_add')}
              onStartSubtract={() => selection.startMode('manual_subtract')}
              onCancel={selection.cancelMode}
              onDeleteCorrection={handleDeleteManualCorrection}
            />
          </div>
        )}

        {detectionRun && detectionRun.status === 'completed' && (
          <div className="card panel" style={{ marginTop: 16 }}>
            <QuantityPanel
              scale={planScale}
              quantity={quantityResult}
              suggestedThicknessMm={activeEntry?.thickness_mm ?? null}
              busy={quantityBusy}
              disabled={false}
              reviewCounts={reviewCounts}
              onConfirmDeclaredScale={handleConfirmDeclaredScale}
              onConfirmCalibratedScale={handleConfirmCalibratedScale}
              onCalculate={handleCalculateQuantity}
              onConfirmResult={handleConfirmQuantityResult}
            />
          </div>
        )}
      </div>
    </div>
  )
}
