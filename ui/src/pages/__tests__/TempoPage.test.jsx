import React from 'react'
import { render, fireEvent, waitFor } from '@testing-library/react'
import TempoPage from '../TempoPage'
import * as api from '../../api'

vi.mock('../../hooks', () => ({ useAutoRefresh: () => {} }))
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 'u1', username: 'me' }, hasPermission: () => true }) }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../../components/ui/PageHeader', () => ({ default: ({ children }) => <div>{children}</div> }))
vi.mock('../../components/ui/AutoRefreshControl', () => ({ default: () => <div /> }))
vi.mock('../../components/ui', () => ({ Card: ({ children }) => <div>{children}</div>, Button: ({ children }) => <button>{children}</button>, Input: (props) => <input {...props} />, Select: ({ children }) => <select>{children}</select>, Spinner: () => <div>Loading</div> }))
vi.mock('../../components/HelpTooltip', () => ({ default: () => <span /> }))

vi.mock('../../api')

describe('TempoPage — fetch limit and pagination', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('uses the configured maxTraces as the query limit', async () => {
    api.fetchTempoServices.mockResolvedValue([])
    api.searchTraces.mockResolvedValue({ data: [] })

    const { getByText } = render(<TempoPage />)

    // change Page Size to 100 and submit
    const label = getByText(/Page Size/i)
    const select = label.parentElement.querySelector('select')
    fireEvent.change(select, { target: { value: '100' } })

    const searchBtn = getByText(/Search Traces/i)
    fireEvent.click(searchBtn)

    await waitFor(() => expect(api.searchTraces).toHaveBeenCalled())
    const lastCall = api.searchTraces.mock.calls[0][0]
    expect(lastCall.limit).toBe(100)
    expect(lastCall.fetchFull).toBe(false)
  })
})