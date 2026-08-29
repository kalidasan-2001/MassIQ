import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import RegionReviewList from './RegionReviewList'

const candidateRegions = [
  { id: 'region-1', similarity: 0.87, status: 'candidate' },
  { id: 'region-2', similarity: 0.7, status: 'candidate' },
]

describe('RegionReviewList', () => {
  it('shows a placeholder before any regions exist', () => {
    render(<RegionReviewList regions={[]} busy={false} onUpdateRegionStatus={vi.fn()} />)
    expect(screen.queryByTestId('detected-region-list')).not.toBeInTheDocument()
    expect(screen.getByText('Run analysis first to see candidate regions here.')).toBeInTheDocument()
  })

  it('renders candidate regions with similarity and accept/reject actions', () => {
    render(<RegionReviewList regions={candidateRegions} busy={false} onUpdateRegionStatus={vi.fn()} />)
    const items = screen.getAllByTestId('detected-region')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('87%')
    expect(screen.getAllByTestId('accept-region-btn')).toHaveLength(2)
    expect(screen.getAllByTestId('reject-region-btn')).toHaveLength(2)
  })

  it('accepting a region calls onUpdateRegionStatus with the region id and "accepted"', async () => {
    const user = userEvent.setup()
    const onUpdateRegionStatus = vi.fn()
    render(<RegionReviewList regions={candidateRegions} busy={false} onUpdateRegionStatus={onUpdateRegionStatus} />)
    await user.click(screen.getAllByTestId('accept-region-btn')[0])
    expect(onUpdateRegionStatus).toHaveBeenCalledWith('region-1', 'accepted')
  })

  it('rejecting a region calls onUpdateRegionStatus with "rejected"', async () => {
    const user = userEvent.setup()
    const onUpdateRegionStatus = vi.fn()
    render(<RegionReviewList regions={candidateRegions} busy={false} onUpdateRegionStatus={onUpdateRegionStatus} />)
    await user.click(screen.getAllByTestId('reject-region-btn')[1])
    expect(onUpdateRegionStatus).toHaveBeenCalledWith('region-2', 'rejected')
  })

  it('a region already decided shows its status instead of action buttons', () => {
    const decided = [{ id: 'region-1', similarity: 0.9, status: 'accepted' }]
    render(<RegionReviewList regions={decided} busy={false} onUpdateRegionStatus={vi.fn()} />)
    expect(screen.queryByTestId('accept-region-btn')).not.toBeInTheDocument()
    expect(screen.getByText('accepted')).toBeInTheDocument()
  })
})
