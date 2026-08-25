import React, { useEffect, useState } from 'react'
import { parseThicknessSuggestionMm } from './materialParsing'

/**
 * OCR text -> user correction -> material confirmation, for one
 * LegendEntry. Deliberately functional, not polished (R3 scope): reuses
 * the app's existing card/panel/field/btn CSS classes rather than
 * inventing new visual design.
 *
 * Provenance rule enforced here at the UI level too (the backend is the
 * real authority): `entry.raw_ocr_text` is shown read-only and is never
 * edited directly -- only `correctedText` (local state, seeded from OCR
 * once, then fully user-owned) is what gets saved as corrected_text.
 */
export default function LegendEntryEditor({
  entry,
  patternCropSrc,
  descriptionCropSrc,
  busy,
  error,
  onRunOcr,
  onSaveCorrection,
  onConfirm,
}) {
  const [correctedText, setCorrectedText] = useState('')
  const [materialName, setMaterialName] = useState('')
  const [materialCode, setMaterialCode] = useState('')
  const [thicknessMm, setThicknessMm] = useState('')

  // Switching to a different entry (or loading one for the first time)
  // resets every local field from that entry's persisted state.
  useEffect(() => {
    setCorrectedText(entry?.corrected_text ?? entry?.raw_ocr_text ?? '')
    setMaterialName(entry?.material_name ?? '')
    setMaterialCode(entry?.material_code ?? '')
    setThicknessMm(entry?.thickness_mm ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entry?.id])

  // Once OCR completes on the *currently loaded* entry, seed the
  // correction field with the fresh OCR text -- but only if the user
  // hasn't already typed something, so a manual entry is never clobbered.
  useEffect(() => {
    if (entry?.raw_ocr_text && !correctedText) {
      setCorrectedText(entry.raw_ocr_text)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entry?.raw_ocr_text])

  if (!entry) {
    return <p className="muted">Select or create a legend entry to begin.</p>
  }

  const suggestedThicknessMm = parseThicknessSuggestionMm(correctedText)
  const isConfirmed = entry.status === 'confirmed'

  const handleSaveCorrection = () => {
    onSaveCorrection?.({
      corrected_text: correctedText,
      material_name: materialName,
      material_code: materialCode || null,
      thickness_mm: thicknessMm === '' ? null : Number(thicknessMm),
    })
  }

  return (
    <div className="card panel">
      <h3>Legend Entry</h3>
      <div className={`status-pill ${isConfirmed ? 'status-completed' : ''}`}>{entry.status}</div>

      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 12 }}>
        <div>
          <p className="muted">Pattern crop</p>
          {patternCropSrc ? (
            <img
              src={patternCropSrc}
              alt="Selected hatch pattern"
              style={{ width: 100, height: 100, objectFit: 'cover', borderRadius: 8, border: '1px solid #cbd7df' }}
            />
          ) : (
            <p className="muted">Not selected yet</p>
          )}
        </div>
        <div>
          <p className="muted">Description crop</p>
          {descriptionCropSrc ? (
            <img
              src={descriptionCropSrc}
              alt="Selected description"
              style={{ width: 180, height: 100, objectFit: 'cover', borderRadius: 8, border: '1px solid #cbd7df' }}
            />
          ) : (
            <p className="muted">Not selected yet</p>
          )}
        </div>
      </div>

      <div className="field" style={{ marginTop: 16 }}>
        <label>Raw OCR text (read-only -- never edited directly)</label>
        <textarea value={entry.raw_ocr_text || ''} readOnly rows={2} />
      </div>
      <button
        type="button"
        className="btn btn-secondary"
        disabled={busy || !entry.has_description_selection}
        onClick={onRunOcr}
      >
        Run OCR
      </button>
      {!entry.has_description_selection && (
        <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
          Select a description region on the plan before running OCR.
        </p>
      )}

      <div className="field" style={{ marginTop: 12 }}>
        <label>Corrected description (this is what gets confirmed)</label>
        <textarea
          value={correctedText}
          onChange={(event) => setCorrectedText(event.target.value)}
          rows={2}
          data-testid="corrected-text-input"
        />
      </div>
      <div className="field">
        <label>Material name</label>
        <input
          value={materialName}
          onChange={(event) => setMaterialName(event.target.value)}
          data-testid="material-name-input"
        />
      </div>
      <div className="field">
        <label>Material code (optional)</label>
        <input value={materialCode} onChange={(event) => setMaterialCode(event.target.value)} />
      </div>
      <div className="field">
        <label>Thickness (mm)</label>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="number"
            value={thicknessMm}
            onChange={(event) => setThicknessMm(event.target.value)}
            style={{ width: 120 }}
          />
          {suggestedThicknessMm != null && Number(thicknessMm) !== suggestedThicknessMm && (
            <button type="button" className="btn btn-secondary" onClick={() => setThicknessMm(suggestedThicknessMm)}>
              Use suggested {suggestedThicknessMm} mm
            </button>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 10, marginTop: 12, flexWrap: 'wrap' }}>
        <button type="button" className="btn" disabled={busy} onClick={handleSaveCorrection} data-testid="save-correction-btn">
          Save Correction &amp; Material
        </button>
        <button
          type="button"
          className="btn"
          disabled={busy || isConfirmed}
          onClick={onConfirm}
          data-testid="confirm-btn"
        >
          {isConfirmed ? 'Confirmed' : 'Confirm Legend Entry'}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </div>
  )
}
