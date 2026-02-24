import React from 'react'
import { render, waitFor } from '@testing-library/react'
import { vi, describe, it, beforeEach, expect } from 'vitest'

vi.mock('../../api', () => ({
  getLabels: vi.fn(),
  getLabelValues: vi.fn(),
  queryLogs: vi.fn(),
  getLogVolume: vi.fn(),
}))

vi.mock('../../components/ui', () => ({
  Card: ({ children }) => <div>{children}</div>,
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: (props) => <input {...props} />,
  Alert: ({ children }) => <div>{children}</div>,
  Sparkline: () => <svg />,
  Spinner: () => <div />,
  Badge: ({ children }) => <span>{children}</span>,
}))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../../hooks', () => ({ useAutoRefresh: () => {}, }))

import LokiPage from '../LokiPage'
import * as api from '../../api'

const STORAGE_KEY = 'lokiPageState'

describe('LokiPage persistence', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('clears saved selectedLabel when it no longer exists', async () => {
    // previous session saved a label that isn't returned by getLabels
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      selectedLabel: 'foo',
      selectedValue: 'bar',
    }))

    api.getLabels.mockResolvedValue({ data: ['baz'] })
    api.getLabelValues.mockResolvedValue({ data: [] })
    render(<LokiPage />)

    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
      expect(stored.selectedLabel).toBeUndefined()
      expect(stored.selectedValue).toBeUndefined()
    })
  })
})
