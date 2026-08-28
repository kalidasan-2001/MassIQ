import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import QuantityPanel from './QuantityPanel'

const reviewCounts = { candidate: 1, accepted: 2, rejected: 1, manualAdd: 1, manualSubtract: 0 }

const baseProps = {
  scale: null,
  quantity: null,
  suggestedThicknessMm: null,
  busy: false,
  disabled: false,
  reviewCounts,
  onConfirmDeclaredScale: vi.fn(),
  onConfirmCalibratedScale: vi.fn(),
  onCalculate: vi.fn(),
  onConfirmResult: vi.fn(),
}

describe('QuantityPanel', () => {
  it('shows scale as not confirmed initially', () => {
    render(<QuantityPanel {...baseProps} />)
    expect(screen.getByTestId('scale-status')).toHaveTextContent('Not confirmed')
  })

  it('shows review counts', () => {
    render(<QuantityPanel {...baseProps} />)
    const counts = screen.getByTestId('review-counts')
    expect(counts).toHaveTextContent('Candidates 1')
    expect(counts).toHaveTextContent('Accepted 2')
    expect(counts).toHaveTextContent('Rejected 1')
    expect(counts).toHaveTextContent('Manual additions 1')
    expect(counts).toHaveTextContent('Manual subtractions 0')
  })

  it('confirming a declared scale calls onConfirmDeclaredScale with the numeric ratio', async () => {
    const user = userEvent.setup()
    const onConfirmDeclaredScale = vi.fn()
    render(<QuantityPanel {...baseProps} onConfirmDeclaredScale={onConfirmDeclaredScale} />)
    await user.clear(screen.getByTestId('declared-ratio-input'))
    await user.type(screen.getByTestId('declared-ratio-input'), '50')
    await user.click(screen.getByTestId('confirm-scale-btn'))
    expect(onConfirmDeclaredScale).toHaveBeenCalledWith(50)
  })

  it('switching to calibrated distance and confirming calls onConfirmCalibratedScale with both numbers', async () => {
    const user = userEvent.setup()
    const onConfirmCalibratedScale = vi.fn()
    render(<QuantityPanel {...baseProps} onConfirmCalibratedScale={onConfirmCalibratedScale} />)
    await user.selectOptions(screen.getByTestId('scale-method-select'), 'calibrated_distance')
    await user.type(screen.getByTestId('calibrated-plan-points-input'), '100')
    await user.type(screen.getByTestId('calibrated-real-m-input'), '5')
    await user.click(screen.getByTestId('confirm-scale-btn'))
    expect(onConfirmCalibratedScale).toHaveBeenCalledWith(100, 5)
  })

  it('shows scale confirmed status once a scale is present', () => {
    render(<QuantityPanel {...baseProps} scale={{ method: 'declared_scale', declared_ratio: 100 }} />)
    expect(screen.getByTestId('scale-status')).toHaveTextContent('Confirmed')
  })

  it('the Calculate button is disabled until a scale is confirmed', () => {
    render(<QuantityPanel {...baseProps} scale={null} />)
    expect(screen.getByTestId('calculate-quantity-btn')).toBeDisabled()
  })

  it('calculating calls onCalculate with the numeric dimension once a scale exists', async () => {
    const user = userEvent.setup()
    const onCalculate = vi.fn()
    render(
      <QuantityPanel
        {...baseProps}
        scale={{ method: 'declared_scale', declared_ratio: 100 }}
        onCalculate={onCalculate}
      />
    )
    await user.type(screen.getByTestId('confirmed-dimension-input'), '2.5')
    await user.click(screen.getByTestId('calculate-quantity-btn'))
    expect(onCalculate).toHaveBeenCalledWith(2.5)
  })

  it('shows a suggested dimension button derived from thickness_mm, never auto-applied', () => {
    render(<QuantityPanel {...baseProps} suggestedThicknessMm={200} />)
    expect(screen.getByText('Use suggested 0.2 m')).toBeInTheDocument()
    // Never silently applied -- the input itself stays whatever the user left it as.
    expect(screen.getByTestId('confirmed-dimension-input')).toHaveValue(null)
  })

  it('displays area/dimension/volume once a quantity result exists', () => {
    render(
      <QuantityPanel
        {...baseProps}
        quantity={{
          status: 'draft',
          final_area_m2: 12.345,
          confirmed_dimension_m: 2.5,
          volume_m3: 30.8625,
        }}
      />
    )
    expect(screen.getByTestId('quantity-area')).toHaveTextContent('12.35')
    expect(screen.getByTestId('quantity-dimension')).toHaveTextContent('2.500')
    expect(screen.getByTestId('quantity-volume')).toHaveTextContent('30.863')
    expect(screen.getByTestId('quantity-status')).toHaveTextContent('Draft')
  })

  it('distinguishes CONFIRMED from DRAFT and hides the confirm button once confirmed', () => {
    render(
      <QuantityPanel
        {...baseProps}
        quantity={{ status: 'confirmed', final_area_m2: 1, confirmed_dimension_m: 1, volume_m3: 1 }}
      />
    )
    expect(screen.getByTestId('quantity-status')).toHaveTextContent('Confirmed')
    expect(screen.queryByTestId('confirm-quantity-btn')).not.toBeInTheDocument()
  })

  it('confirming a draft result calls onConfirmResult', async () => {
    const user = userEvent.setup()
    const onConfirmResult = vi.fn()
    render(
      <QuantityPanel
        {...baseProps}
        quantity={{ status: 'draft', final_area_m2: 1, confirmed_dimension_m: 1, volume_m3: 1 }}
        onConfirmResult={onConfirmResult}
      />
    )
    await user.click(screen.getByTestId('confirm-quantity-btn'))
    expect(onConfirmResult).toHaveBeenCalledTimes(1)
  })
})
