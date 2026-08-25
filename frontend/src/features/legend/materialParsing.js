// R3: a simple, deterministic thickness-suggestion parser ONLY -- never a
// material classifier. It never writes to a LegendEntry by itself; the
// caller (LegendEntryEditor) only ever shows the suggested value in the
// thickness_mm input for the user to accept, edit, or ignore before
// saving. This is intentionally frontend-only client-side assistance, not
// a backend concern -- see the R3 checklist's "Do not build a global
// taxonomy" note.
//
// Recognizes obvious "d=20cm" / "d = 20 cm" / "20cm" / "200mm" style
// patterns commonly seen in German construction-drawing legends.

const CM_PATTERN = /\bd\s*=\s*(\d+(?:[.,]\d+)?)\s*cm\b|\b(\d+(?:[.,]\d+)?)\s*cm\b/i
const MM_PATTERN = /\bd\s*=\s*(\d+(?:[.,]\d+)?)\s*mm\b|\b(\d+(?:[.,]\d+)?)\s*mm\b/i

export function parseThicknessSuggestionMm(text) {
  if (!text) return null

  const mmMatch = text.match(MM_PATTERN)
  if (mmMatch) {
    const value = Number((mmMatch[1] || mmMatch[2]).replace(',', '.'))
    return Number.isFinite(value) ? value : null
  }

  const cmMatch = text.match(CM_PATTERN)
  if (cmMatch) {
    const value = Number((cmMatch[1] || cmMatch[2]).replace(',', '.'))
    return Number.isFinite(value) ? value * 10 : null
  }

  return null
}
