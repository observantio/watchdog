`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import React from 'react'
import { render, fireEvent, waitFor } from '@testing-library/react'
import TempoPage from '../TempoPage'
import * as api from '../../api'

vi.mock('../../hooks', () => ({ useAutoRefresh: () => {} }))
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 'u1', username: 'me' }, hasPermission: () => true }) }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../../components/ui/PageHeader', () => ({ default: ({ children }) => <div>{children}</div> }))
vi.mock('../../components/ui/AutoRefreshControl', () => ({ default: () => <div /> }))
vi.mock('../../components/ui', () => ({ Card: ({ children }) => <div>{children}</div>, Button: ({ children }) => <button>{children}</button>, Input: (props) => <input {...props} />, Select: ({ children }) => <select>{children}</select>, Spinner: () => <div>Loading</div>, Badge: ({ children }) => <span>{children}</span>, Alert: ({ children }) => <div>{children}</div> }))
vi.mock('../../components/HelpTooltip', () => ({ default: () => <span /> }))

vi.mock('../../api')

describe('TempoPage — fetch limit and pagination', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('allows a separate search limit (max traces) and sends it to the API', async () => {
    api.fetchTempoServices.mockResolvedValue([])
    api.searchTraces.mockResolvedValue({ data: [] })

    const { getByText } = render(<TempoPage />)

    // change Search Limit to 50 and submit
    const limitLabel = getByText(/Search Limit/i)
    const limitSelect = limitLabel.parentElement.querySelector('select')
    fireEvent.change(limitSelect, { target: { value: '50' } })

    const searchBtn = getByText(/Search Traces/i)
    fireEvent.click(searchBtn)

    await waitFor(() => expect(api.searchTraces).toHaveBeenCalled())
    const lastCall = api.searchTraces.mock.calls[0][0]
    expect(lastCall.limit).toBe(50)
    expect(lastCall.fetchFull).toBe(false)
  })

  it('calculates total pages based on pageSize and shows pagination info', async () => {
    api.fetchTempoServices.mockResolvedValue([])
    // create 45 fake traces
    const fakeTraces = Array.from({ length: 45 }, (_, i) => ({ traceID: `t${i}` }))
    api.searchTraces.mockResolvedValue({ data: fakeTraces })

    const { getByText } = render(<TempoPage />)
    const searchBtn = getByText(/Search Traces/i)
    fireEvent.click(searchBtn)

    await waitFor(() => expect(api.searchTraces).toHaveBeenCalled())

    // default pageSize is 20 so we expect 3 pages; wait for the pagination text to appear
    await waitFor(() => {
      expect(getByText(/Page 1 of 3/)).toBeInTheDocument()
    })
  })

  it('restores filters and triggers search from localStorage on mount', async () => {
    // store a saved state containing a service filter (no traceId) before rendering
    const saved = {
      service: 'svc',
      viewMode: 'list',
    }
    localStorage.setItem('tempoPageState', JSON.stringify(saved))

    api.fetchTempoServices.mockResolvedValue([])
    api.searchTraces.mockResolvedValue({ data: [] })

    render(<TempoPage />)

    // on mount the component should perform a search due to saved service filter
    await waitFor(() => expect(api.searchTraces).toHaveBeenCalled())
    const call = api.searchTraces.mock.calls[0][0]
    expect(call.service).toBe('svc')
  })

  it('silently clears a saved trace id if the trace no longer exists', async () => {
    // prepare saved state with a nonexistent trace
    const saved = { selectedTrace: 'missing' }
    localStorage.setItem('tempoPageState', JSON.stringify(saved))

    api.fetchTempoServices.mockResolvedValue([])
    api.searchTraces.mockResolvedValue({ data: [] })
    const err = new Error('not found')
    err.status = 404
    api.getTrace.mockRejectedValue(err)

    const { queryByText } = render(<TempoPage />)
    // component should attempt to load and then clear state
    await waitFor(() => expect(api.getTrace).toHaveBeenCalledWith('missing'))
    expect(queryByText(/Failed to load trace/)).not.toBeInTheDocument()

    const stored = JSON.parse(localStorage.getItem('tempoPageState') || '{}')
    expect(stored.selectedTrace).toBeFalsy()
  })
})