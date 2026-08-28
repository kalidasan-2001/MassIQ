import React from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ResultsPanel from './ResultsPanel'
import * as legendApi from '../legend/api'

vi.mock('../legend/api')

const confirmedRow = {
  quantity_result_id: 'result-1',
  plan_name: 'Ground Floor.pdf',
  page_number: 1,
  material_name: 'Stahlbeton C25/30',
  material_code: 'C25/30',
  area_m2: 84.2,
  confirmed_dimension_m: 0.2,
  volume_m3: 16.84,
  status: 'confirmed',
  calculation_version: '1.0',
  accepted_region_count: 5,
  rejected_region_count: 2,
  manual_add_count: 1,
  manual_subtract_count: 2,
}

const draftRow = {
  ...confirmedRow,
  quantity_result_id: 'result-2',
  material_name: 'Draft Material',
  status: 'draft',
}

beforeEach(() => {
  vi.resetAllMocks()
})

describe('ResultsPanel', () => {
  it('shows an empty state when there are no results', async () => {
    legendApi.listResults.mockResolvedValue([])
    legendApi.exportPreflight.mockResolvedValue({ confirmed_count: 0, can_export: false })
    render(<ResultsPanel projectId="p1" refreshKey={0} />)
    await waitFor(() => expect(screen.getByTestId('results-empty')).toBeInTheDocument())
  })

  it('renders result rows with plan/material/area/dimension/volume/status', async () => {
    legendApi.listResults.mockResolvedValue([confirmedRow])
    legendApi.exportPreflight.mockResolvedValue({ confirmed_count: 1, can_export: true })
    render(<ResultsPanel projectId="p1" refreshKey={0} />)
    await waitFor(() => expect(screen.getByTestId('results-table')).toBeInTheDocument())
    expect(screen.getByText('Ground Floor.pdf')).toBeInTheDocument()
    expect(screen.getByText('Stahlbeton C25/30')).toBeInTheDocument()
    expect(screen.getByTestId('result-area')).toHaveTextContent('84.20')
    expect(screen.getByTestId('result-volume')).toHaveTextContent('16.840')
  })

  it('distinguishes confirmed from draft with visible text, not color alone', async () => {
    legendApi.listResults.mockResolvedValue([confirmedRow, draftRow])
    legendApi.exportPreflight.mockResolvedValue({ confirmed_count: 1, can_export: true })
    render(<ResultsPanel projectId="p1" refreshKey={0} />)
    await waitFor(() => expect(screen.getAllByTestId('result-status')).toHaveLength(2))
    const labels = screen.getAllByTestId('result-status').map((el) => el.textContent)
    expect(labels).toContain('Confirmed')
    expect(labels).toContain('Draft')
  })

  it('the export button shows the confirmed count and is disabled at zero', async () => {
    legendApi.listResults.mockResolvedValue([draftRow])
    legendApi.exportPreflight.mockResolvedValue({ confirmed_count: 0, can_export: false })
    render(<ResultsPanel projectId="p1" refreshKey={0} />)
    await waitFor(() => expect(screen.getByTestId('export-results-btn')).toHaveTextContent('(0)'))
    expect(screen.getByTestId('export-results-btn')).toBeDisabled()
    expect(screen.getByTestId('export-disabled-hint')).toBeInTheDocument()
  })

  it('the export button is enabled and labeled with the confirmed count', async () => {
    legendApi.listResults.mockResolvedValue([confirmedRow])
    legendApi.exportPreflight.mockResolvedValue({ confirmed_count: 1, can_export: true })
    render(<ResultsPanel projectId="p1" refreshKey={0} />)
    await waitFor(() => expect(screen.getByTestId('export-results-btn')).toHaveTextContent('(1)'))
    expect(screen.getByTestId('export-results-btn')).not.toBeDisabled()
  })

  it('clicking Details expands the provenance panel', async () => {
    const user = userEvent.setup()
    legendApi.listResults.mockResolvedValue([confirmedRow])
    legendApi.exportPreflight.mockResolvedValue({ confirmed_count: 1, can_export: true })
    render(<ResultsPanel projectId="p1" refreshKey={0} />)
    await waitFor(() => expect(screen.getByTestId('result-details-btn')).toBeInTheDocument())
    expect(screen.queryByTestId('result-details-panel')).not.toBeInTheDocument()
    await user.click(screen.getByTestId('result-details-btn'))
    expect(screen.getByTestId('result-details-panel')).toBeInTheDocument()
    expect(screen.getByText(/Accepted regions: 5/)).toBeInTheDocument()
    expect(screen.getByText(/Manual additions: 1/)).toBeInTheDocument()
  })

  it('shows an error state when loading fails', async () => {
    legendApi.listResults.mockRejectedValue({ message: 'Network error' })
    legendApi.exportPreflight.mockResolvedValue({ confirmed_count: 0, can_export: false })
    render(<ResultsPanel projectId="p1" refreshKey={0} />)
    await waitFor(() => expect(screen.getByText('Network error')).toBeInTheDocument())
  })

  it('exporting triggers a real download click with the server-provided filename', async () => {
    const user = userEvent.setup()
    legendApi.listResults.mockResolvedValue([confirmedRow])
    legendApi.exportPreflight.mockResolvedValue({ confirmed_count: 1, can_export: true })
    legendApi.exportResults.mockResolvedValue({
      data: new Blob(['fake xlsx bytes']),
      headers: { 'content-disposition': 'attachment; filename="MassIQ_Test_quantities_20260828.xlsx"' },
    })

    const originalCreateObjectURL = window.URL.createObjectURL
    const originalRevokeObjectURL = window.URL.revokeObjectURL
    window.URL.createObjectURL = vi.fn(() => 'blob:mock-url')
    window.URL.revokeObjectURL = vi.fn()
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    render(<ResultsPanel projectId="p1" refreshKey={0} />)
    await waitFor(() => expect(screen.getByTestId('export-results-btn')).not.toBeDisabled())
    await user.click(screen.getByTestId('export-results-btn'))

    await waitFor(() => expect(clickSpy).toHaveBeenCalled())
    expect(legendApi.exportResults).toHaveBeenCalledWith('p1')

    clickSpy.mockRestore()
    window.URL.createObjectURL = originalCreateObjectURL
    window.URL.revokeObjectURL = originalRevokeObjectURL
  })
})
