import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
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
}))
vi.mock('../components/loki/LogQueryForm', () => ({ default: () => <div /> }))
vi.mock('../components/loki/LogResults', () => ({ default: () => <div /> }))
vi.mock('../components/loki/LogVolume', () => ({ default: () => <div /> }))
vi.mock('../components/loki/LogQuickFilters', () => ({ default: () => <div /> }))
vi.mock('../components/loki/LogLabels', () => ({ default: () => <div /> }))
vi.mock('../components/HelpTooltip', () => ({ default: () => <span /> }))

import * as api from '../api'

describe('LokiPage performance behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('prefetches label values with cap during initial load', async () => {
    const labels = Array.from({ length: 20 }, (_, i) => `label_${i}`)
    api.getLabels.mockResolvedValue({ data: labels })
    api.getLabelValues.mockImplementation(async (label) => ({ data: [`${label}_value`] }))

    render(<LokiPage />)

    await waitFor(() => expect(api.getLabels).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(api.getLabelValues).toHaveBeenCalledTimes(12))
  })
})
