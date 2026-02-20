import React from 'react'
import { render, fireEvent, waitFor } from '@testing-library/react'

// mocks similar to other page tests
vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks')
  return {
    ...actual,
    useAlertManagerData: () => ({
      alerts: [],
      silences: [],
      rules: [],
      channels: [],
      loading: false,
      error: null,
      reloadData: vi.fn(),
      setError: vi.fn(),
    }),
  }
})
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ user: { api_keys: [] }, hasPermission: () => true }) }))

import AlertManagerPage from '../AlertManagerPage'
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: { success: vi.fn(), error: vi.fn() } }) }))
vi.mock('../components/ui', () => ({
  Card: ({ children }) => <div>{children}</div>,
  Button: ({ children }) => <button>{children}</button>,
  Select: (props) => <select {...props} />,
  Alert: ({ children }) => <div>{children}</div>,
  Spinner: () => <div>Loading</div>,
}))
vi.mock('../components/ConfirmModal', () => ({ default: () => <div /> }))
vi.mock('../components/HelpTooltip', () => ({ default: () => <span /> }))
vi.mock('../components/alertmanager/RuleEditor', () => ({ default: () => <div /> }))
vi.mock('../components/alertmanager/SilenceForm', () => ({ default: () => <div /> }))

// ensure our simple useLocalStorage returns state that updates localStorage correctly
let realUseLocalStorage
beforeAll(async () => {
  const actual = await vi.importActual('../../hooks')
  realUseLocalStorage = actual.useLocalStorage
})

describe('AlertManagerPage state persistence', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('respects activeTab stored in localStorage', () => {
    localStorage.setItem('alertmanager-active-tab', JSON.stringify('rules'))
    const { getByText } = render(<AlertManagerPage />)
    // 'Rules' button should be styled as active (border or primary)
    const rulesBtn = getByText(/Rules/i)
    expect(rulesBtn).toHaveClass('text-sre-primary')
  })

  it('updates localStorage when tab changes', () => {
    const { getByText } = render(<AlertManagerPage />)
    const silencesBtn = getByText(/Silences/i)
    fireEvent.click(silencesBtn)
    expect(JSON.parse(localStorage.getItem('alertmanager-active-tab'))).toBe('silences')
  })
})
