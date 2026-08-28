import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import DetectionPanel from './DetectionPanel'

const completedRun = {
  status: 'completed',
  tiles_evaluated: 12,
  tiles_skipped: 40,
  candidate_region_count: 2,
}

const candidateRegions = [
  { id: 'region-1', similarity: 0.87, status: 'candidate' },
  { id: 'region-2', similarity: 0.7, status: 'candidate' },
]

describe('DetectionPanel', () => {
  it('renders a Run Detection V2 button before any run exists', () => {
    render(<DetectionPanel run={null} regions={[]} busy={false} disabled={false} onRunDetection={vi.fn()} onUpdateRegionStatus={vi.fn()} />)
    expect(screen.getByTestId('run-detection-btn')).toBeInTheDocument()
    expect(screen.queryByTestId('detected-region-list')).not.toBeInTheDocument()
  })

  it('calls onRunDetection when the button is clicked', async () => {
    const user = userEvent.setup()
    const onRunDetection = vi.fn()
    render(<DetectionPanel run={null} regions={[]} busy={false} disabled={false} onRunDetection={onRunDetection} onUpdateRegionStatus={vi.fn()} />)
    await user.click(screen.getByTestId('run-detection-btn'))
    expect(onRunDetection).toHaveBeenCalledTimes(1)
  })

  it('renders candidate regions with similarity and accept/reject actions', () => {
    render(
      <DetectionPanel
        run={completedRun}
        regions={candidateRegions}
        busy={false}
        disabled={false}
        onRunDetection={vi.fn()}
        onUpdateRegionStatus={vi.fn()}
      />
    )
    const items = screen.getAllByTestId('detected-region')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('87%')
    expect(screen.getAllByTestId('accept-region-btn')).toHaveLength(2)
    expect(screen.getAllByTestId('reject-region-btn')).toHaveLength(2)
  })

  it('accepting a region calls onUpdateRegionStatus with the region id and "accepted"', async () => {
    const user = userEvent.setup()
    const onUpdateRegionStatus = vi.fn()
    render(
      <DetectionPanel
        run={completedRun}
        regions={candidateRegions}
        busy={false}
        disabled={false}
        onRunDetection={vi.fn()}
        onUpdateRegionStatus={onUpdateRegionStatus}
      />
    )
    await user.click(screen.getAllByTestId('accept-region-btn')[0])
    expect(onUpdateRegionStatus).toHaveBeenCalledWith('region-1', 'accepted')
  })

  it('rejecting a region calls onUpdateRegionStatus with "rejected"', async () => {
    const user = userEvent.setup()
    const onUpdateRegionStatus = vi.fn()
    render(
      <DetectionPanel
        run={completedRun}
        regions={candidateRegions}
        busy={false}
        disabled={false}
        onRunDetection={vi.fn()}
        onUpdateRegionStatus={onUpdateRegionStatus}
      />
    )
    await user.click(screen.getAllByTestId('reject-region-btn')[1])
    expect(onUpdateRegionStatus).toHaveBeenCalledWith('region-2', 'rejected')
  })

  it('a region already decided shows its status instead of action buttons', () => {
    const decided = [{ id: 'region-1', similarity: 0.9, status: 'accepted' }]
    render(
      <DetectionPanel
        run={completedRun}
        regions={decided}
        busy={false}
        disabled={false}
        onRunDetection={vi.fn()}
        onUpdateRegionStatus={vi.fn()}
      />
    )
    expect(screen.queryByTestId('accept-region-btn')).not.toBeInTheDocument()
    expect(screen.getByText('accepted')).toBeInTheDocument()
  })

  it('shows the failure message when the run failed', () => {
    render(
      <DetectionPanel
        run={{ status: 'failed', error_message: 'Detection failed while processing the page image.' }}
        regions={[]}
        busy={false}
        disabled={false}
        onRunDetection={vi.fn()}
        onUpdateRegionStatus={vi.fn()}
      />
    )
    expect(screen.getByText('Detection failed while processing the page image.')).toBeInTheDocument()
  })
})
