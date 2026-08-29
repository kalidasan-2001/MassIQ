import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ScaleConfirmationPanel from './ScaleConfirmationPanel'

const baseProps = {
  scale: null,
  busy: false,
  disabled: false,
  onConfirmDeclaredScale: vi.fn(),
  onConfirmCalibratedScale: vi.fn(),
}

describe('ScaleConfirmationPanel', () => {
  it('shows scale as not confirmed initially', () => {
    render(<ScaleConfirmationPanel {...baseProps} />)
    expect(screen.getByTestId('scale-status')).toHaveTextContent('Not confirmed')
  })

  it('confirming a declared scale calls onConfirmDeclaredScale with the numeric ratio', async () => {
    const user = userEvent.setup()
    const onConfirmDeclaredScale = vi.fn()
    render(<ScaleConfirmationPanel {...baseProps} onConfirmDeclaredScale={onConfirmDeclaredScale} />)
    await user.clear(screen.getByTestId('declared-ratio-input'))
    await user.type(screen.getByTestId('declared-ratio-input'), '50')
    await user.click(screen.getByTestId('confirm-scale-btn'))
    expect(onConfirmDeclaredScale).toHaveBeenCalledWith(50)
  })

  it('switching to calibrated distance and confirming calls onConfirmCalibratedScale with both numbers', async () => {
    const user = userEvent.setup()
    const onConfirmCalibratedScale = vi.fn()
    render(<ScaleConfirmationPanel {...baseProps} onConfirmCalibratedScale={onConfirmCalibratedScale} />)
    await user.selectOptions(screen.getByTestId('scale-method-select'), 'calibrated_distance')
    await user.type(screen.getByTestId('calibrated-plan-points-input'), '100')
    await user.type(screen.getByTestId('calibrated-real-m-input'), '5')
    await user.click(screen.getByTestId('confirm-scale-btn'))
    expect(onConfirmCalibratedScale).toHaveBeenCalledWith(100, 5)
  })

  it('shows scale confirmed status once a scale is present', () => {
    render(<ScaleConfirmationPanel {...baseProps} scale={{ method: 'declared_scale', declared_ratio: 100 }} />)
    expect(screen.getByTestId('scale-status')).toHaveTextContent('Confirmed')
  })
})
