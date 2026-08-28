import React, { useEffect, useMemo, useState } from 'react'
import { normalizedToDisplayRect } from './coordinates'
import { usePageSelection } from './usePageSelection'
import { useLegendEntries } from './useLegendEntries'
import LegendSelectionToolbar from './LegendSelectionToolbar'
import LegendEntryEditor from './LegendEntryEditor'
import LegendEntryList from './LegendEntryList'
import * as legendApi from './api'

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

  const handleRegionComplete = async (mode, normalizedRect) => {
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
            ? `Drawing ${selection.mode} selection -- drag a rectangle on the page.`
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
      </div>
    </div>
  )
}
