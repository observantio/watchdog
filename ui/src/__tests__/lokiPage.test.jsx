import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor, fireEvent } from '@testing-library/react'
import LokiPage from '../pages/LokiPage'

vi.mock('../hooks', () => ({
  useAutoRefresh: () => {},
}))

vi.mock('../contexts/ToastContext', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}))

vi.mock('../api', () => ({
  getLabels: vi.fn(),
  getLabelValues: vi.fn(),
  queryLogs: vi.fn(),
  getLogVolume: vi.fn(),
}))

vi.mock('../components/ui/PageHeader', () => ({ default: ({ children }) => <div>{children}</div> }))
vi.mock('../components/ui/AutoRefreshControl', () => ({ default: () => <div /> }))
vi.mock('../components/ui', () => ({
  Card: ({ children }) => <div>{children}</div>,
  Button: ({ children }) => <button>{children}</button>,
  Alert: ({ children }) => <div>{children}</div>,
  Spinner: () => <div>Loading</div>,
  // tests reference Badge in LogResults, make sure mock exports it
  Badge: ({ children }) => <span>{children}</span>,
}))
// use real query form/results to exercise new controls
// mocks still exist for subordinate components we don't care about
// (LogVolume, LogQuickFilters, LogLabels)
//
// vi.mock('../components/loki/LogQueryForm', () => ({ default: () => <div /> }))
// vi.mock('../components/loki/LogResults', () => ({ default: () => <div /> }))
vi.mock('../components/loki/LogVolume', () => ({ default: () => <div /> }))
vi.mock('../components/loki/LogQuickFilters', () => ({ default: () => <div /> }))
vi.mock('../components/loki/LogLabels', () => ({ default: () => <div /> }))
vi.mock('../components/HelpTooltip', () => ({ default: () => <span /> }))

import * as api from '../api'

describe('LokiPage performance behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('prefetches label values with cap during initial load', async () => {
    const labels = Array.from({ length: 20 }, (_, i) => `label_${i}`)
    api.getLabels.mockResolvedValue({ data: labels })
    api.getLabelValues.mockImplementation(async (label) => ({ data: [`${label}_value`] }))

    render(<LokiPage />)

    await waitFor(() => expect(api.getLabels).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(api.getLabelValues).toHaveBeenCalledTimes(12))
  })

  it('uses search limit and page size and paginates results', async () => {
    api.getLabels.mockResolvedValue({ data: [] })
    // generate 45 dummy streams each with one log value
    const fakeStreams = Array.from({ length: 45 }, (_, i) => ({ stream: {}, values: [[i, `log${i}`]] }))
    api.queryLogs.mockResolvedValue({ data: { result: fakeStreams } })

    const { getByText } = render(<LokiPage />)

    // change Search Limit to 50
    const limitLabel = getByText(/Search Limit/i)
    const limitSelect = limitLabel.parentElement.querySelector('select')
    fireEvent.change(limitSelect, { target: { value: '50' } })

    // change Page Size to 20
    const pageSizeLabel = getByText(/Page Size/i)
    // the select we want is immediately after the label, not just the first select in the parent
    const pageSizeSelect = pageSizeLabel.nextElementSibling
    fireEvent.change(pageSizeSelect, { target: { value: '20' } })

    const runBtn = getByText(/Run Query/i)
    fireEvent.click(runBtn)

    await waitFor(() => expect(api.queryLogs).toHaveBeenCalled())
    const lastCall = api.queryLogs.mock.calls[0][0]
    expect(lastCall.limit).toBe(50)

    // pagination summary should reflect pageSize
    await waitFor(() => expect(getByText(/Showing 1–20 of 45 streams/)).toBeInTheDocument())
  })

  it('restores filters from localStorage and triggers a query on mount', async () => {
    const saved = { selectedFilters: [{ label: 'foo', value: 'bar' }], searchLimit: 10 }
    localStorage.setItem('lokiPageState', JSON.stringify(saved))
    api.getLabels.mockResolvedValue({ data: [] })
    api.queryLogs.mockResolvedValue({ data: { result: [] } })

    render(<LokiPage />)

    await waitFor(() => expect(api.queryLogs).toHaveBeenCalled())
    const call = api.queryLogs.mock.calls[0][0]
    expect(call.limit).toBe(10)
  })

})
