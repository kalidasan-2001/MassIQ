import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DetectionRunPanel from './DetectionRunPanel'

const completedRun = {
  status: 'completed',
  tiles_evaluated: 12,
  tiles_skipped: 40,
  candidate_region_count: 2,
}

describe('DetectionRunPanel', () => {
  it('renders a Run Detection V2 button before any run exists', () => {
    render(<DetectionRunPanel run={null} busy={false} disabled={false} onRunDetection={vi.fn()} />)
    expect(screen.getByTestId('run-detection-btn')).toBeInTheDocument()
  })

  it('calls onRunDetection when the button is clicked', async () => {
    const user = userEvent.setup()
    const onRunDetection = vi.fn()
    render(<DetectionRunPanel run={null} busy={false} disabled={false} onRunDetection={onRunDetection} />)
    await user.click(screen.getByTestId('run-detection-btn'))
    expect(onRunDetection).toHaveBeenCalledTimes(1)
  })

  it('shows tile/candidate counts once the run completes', () => {
    render(<DetectionRunPanel run={completedRun} busy={false} disabled={false} onRunDetection={vi.fn()} />)
    expect(screen.getByText(/2 candidate regions found/)).toBeInTheDocument()
  })

  it('shows the failure message when the run failed', () => {
    render(
      <DetectionRunPanel
        run={{ status: 'failed', error_message: 'Detection failed while processing the page image.' }}
        busy={false}
        disabled={false}
        onRunDetection={vi.fn()}
      />
    )
    expect(screen.getByText('Detection failed while processing the page image.')).toBeInTheDocument()
  })
})
