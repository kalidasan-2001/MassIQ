import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ManualCorrectionPanel from './ManualCorrectionPanel'

const corrections = [
  { id: 'corr-1', correction_type: 'add' },
  { id: 'corr-2', correction_type: 'subtract' },
]

describe('ManualCorrectionPanel', () => {
  it('renders Manual Add / Manual Subtract buttons', () => {
    render(
      <ManualCorrectionPanel
        mode={null}
        corrections={[]}
        busy={false}
        disabled={false}
        onStartAdd={vi.fn()}
        onStartSubtract={vi.fn()}
        onCancel={vi.fn()}
        onDeleteCorrection={vi.fn()}
      />
    )
    expect(screen.getByTestId('manual-add-btn')).toBeInTheDocument()
    expect(screen.getByTestId('manual-subtract-btn')).toBeInTheDocument()
    expect(screen.queryByTestId('manual-cancel-btn')).not.toBeInTheDocument()
  })

  it('calls onStartAdd when Manual Add is clicked', async () => {
    const user = userEvent.setup()
    const onStartAdd = vi.fn()
    render(
      <ManualCorrectionPanel
        mode={null}
        corrections={[]}
        busy={false}
        disabled={false}
        onStartAdd={onStartAdd}
        onStartSubtract={vi.fn()}
        onCancel={vi.fn()}
        onDeleteCorrection={vi.fn()}
      />
    )
    await user.click(screen.getByTestId('manual-add-btn'))
    expect(onStartAdd).toHaveBeenCalledTimes(1)
  })

  it('calls onStartSubtract when Manual Subtract is clicked', async () => {
    const user = userEvent.setup()
    const onStartSubtract = vi.fn()
    render(
      <ManualCorrectionPanel
        mode={null}
        corrections={[]}
        busy={false}
        disabled={false}
        onStartAdd={vi.fn()}
        onStartSubtract={onStartSubtract}
        onCancel={vi.fn()}
        onDeleteCorrection={vi.fn()}
      />
    )
    await user.click(screen.getByTestId('manual-subtract-btn'))
    expect(onStartSubtract).toHaveBeenCalledTimes(1)
  })

  it('shows a Cancel button while a mode is active', () => {
    render(
      <ManualCorrectionPanel
        mode="manual_add"
        corrections={[]}
        busy={false}
        disabled={false}
        onStartAdd={vi.fn()}
        onStartSubtract={vi.fn()}
        onCancel={vi.fn()}
        onDeleteCorrection={vi.fn()}
      />
    )
    expect(screen.getByTestId('manual-cancel-btn')).toBeInTheDocument()
  })

  it('renders each correction with an explicit Added/Subtracted label, not just a color', () => {
    render(
      <ManualCorrectionPanel
        mode={null}
        corrections={corrections}
        busy={false}
        disabled={false}
        onStartAdd={vi.fn()}
        onStartSubtract={vi.fn()}
        onCancel={vi.fn()}
        onDeleteCorrection={vi.fn()}
      />
    )
    const labels = screen.getAllByTestId('manual-correction-label')
    expect(labels).toHaveLength(2)
    expect(labels[0]).toHaveTextContent('Added')
    expect(labels[1]).toHaveTextContent('Subtracted')
  })

  it('shows accurate addition/subtraction counts', () => {
    render(
      <ManualCorrectionPanel
        mode={null}
        corrections={corrections}
        busy={false}
        disabled={false}
        onStartAdd={vi.fn()}
        onStartSubtract={vi.fn()}
        onCancel={vi.fn()}
        onDeleteCorrection={vi.fn()}
      />
    )
    expect(screen.getByTestId('manual-correction-counts')).toHaveTextContent('1 manual addition')
    expect(screen.getByTestId('manual-correction-counts')).toHaveTextContent('1 manual subtraction')
  })

  it('deleting a correction calls onDeleteCorrection with its id', async () => {
    const user = userEvent.setup()
    const onDeleteCorrection = vi.fn()
    render(
      <ManualCorrectionPanel
        mode={null}
        corrections={corrections}
        busy={false}
        disabled={false}
        onStartAdd={vi.fn()}
        onStartSubtract={vi.fn()}
        onCancel={vi.fn()}
        onDeleteCorrection={onDeleteCorrection}
      />
    )
    await user.click(screen.getAllByTestId('manual-correction-delete-btn')[0])
    expect(onDeleteCorrection).toHaveBeenCalledWith('corr-1')
  })

  it('disables Add/Subtract buttons when disabled', () => {
    render(
      <ManualCorrectionPanel
        mode={null}
        corrections={[]}
        busy={false}
        disabled
        onStartAdd={vi.fn()}
        onStartSubtract={vi.fn()}
        onCancel={vi.fn()}
        onDeleteCorrection={vi.fn()}
      />
    )
    expect(screen.getByTestId('manual-add-btn')).toBeDisabled()
    expect(screen.getByTestId('manual-subtract-btn')).toBeDisabled()
  })
})
