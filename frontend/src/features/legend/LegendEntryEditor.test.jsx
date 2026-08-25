import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LegendEntryEditor from './LegendEntryEditor'

const baseEntry = {
  id: 'entry-1',
  status: 'ocr_complete',
  raw_ocr_text: 'Stahlbeton C25I30 d=2Ocm', // deliberately OCR-garbled
  corrected_text: null,
  material_name: null,
  material_code: null,
  thickness_mm: null,
  has_pattern_selection: true,
  has_description_selection: true,
}

describe('LegendEntryEditor', () => {
  it('renders a prompt instead of a form when there is no entry yet', () => {
    render(<LegendEntryEditor entry={null} />)
    expect(screen.getByText(/select or create a legend entry/i)).toBeInTheDocument()
  })

  it('seeds the correction field from raw OCR text but keeps it independently editable', () => {
    render(<LegendEntryEditor entry={baseEntry} onSaveCorrection={vi.fn()} onConfirm={vi.fn()} onRunOcr={vi.fn()} />)
    const textarea = screen.getByTestId('corrected-text-input')
    expect(textarea).toHaveValue('Stahlbeton C25I30 d=2Ocm')
  })

  it('uses the user-edited text, not the original OCR text, when saving the correction', async () => {
    const user = userEvent.setup()
    const onSaveCorrection = vi.fn()
    render(
      <LegendEntryEditor
        entry={baseEntry}
        onSaveCorrection={onSaveCorrection}
        onConfirm={vi.fn()}
        onRunOcr={vi.fn()}
      />
    )

    const textarea = screen.getByTestId('corrected-text-input')
    await user.clear(textarea)
    await user.type(textarea, 'Stahlbeton C25/30 d=20cm')

    const materialInput = screen.getByTestId('material-name-input')
    await user.type(materialInput, 'Stahlbeton C25/30')

    await user.click(screen.getByTestId('save-correction-btn'))

    expect(onSaveCorrection).toHaveBeenCalledTimes(1)
    const payload = onSaveCorrection.mock.calls[0][0]
    // The critical assertion: the CONFIRMED value uses the edited text,
    // not the raw OCR text it started from.
    expect(payload.corrected_text).toBe('Stahlbeton C25/30 d=20cm')
    expect(payload.corrected_text).not.toBe(baseEntry.raw_ocr_text)
    expect(payload.material_name).toBe('Stahlbeton C25/30')
  })

  it('disables the confirm button once the entry is already confirmed', () => {
    render(
      <LegendEntryEditor
        entry={{ ...baseEntry, status: 'confirmed', corrected_text: 'Stahlbeton C25/30' }}
        onSaveCorrection={vi.fn()}
        onConfirm={vi.fn()}
        onRunOcr={vi.fn()}
      />
    )
    expect(screen.getByTestId('confirm-btn')).toBeDisabled()
  })

  it('disables Run OCR until a description region has been selected', () => {
    render(
      <LegendEntryEditor
        entry={{ ...baseEntry, has_description_selection: false, raw_ocr_text: null }}
        onSaveCorrection={vi.fn()}
        onConfirm={vi.fn()}
        onRunOcr={vi.fn()}
      />
    )
    expect(screen.getByRole('button', { name: /run ocr/i })).toBeDisabled()
  })
})
