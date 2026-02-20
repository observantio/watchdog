import React from 'react'
import { render, waitFor } from '@testing-library/react'

// minimal mocks for dependencies
vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks')
  return { ...actual }
})
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ user: { api_keys: [] }, hasPermission: () => true }) }))

import GrafanaPage from '../GrafanaPage'
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast: { success: vi.fn(), error: vi.fn() } }) }))
vi.mock('../components/ui', () => ({ Button: ({ children }) => <button>{children}</button>, ConfirmDialog: () => <div /> }))
vi.mock('../components/ui/PageHeader', () => ({ default: ({ children }) => <div>{children}</div> }))
vi.mock('../components/grafana/GrafanaTabs', () => ({ default: ({ activeTab }) => <div data-active={activeTab} /> }))
vi.mock('../components/grafana/GrafanaContent', () => ({ default: () => <div /> }))

vi.mock('../api', () => ({
  searchDashboards: vi.fn().mockResolvedValue([]),
  getDatasources: vi.fn().mockResolvedValue([]),
  getFolders: vi.fn().mockResolvedValue([]),
  getGroups: vi.fn().mockResolvedValue([]),
  getDashboardFilterMeta: vi.fn().mockResolvedValue({}),
  getDatasourceFilterMeta: vi.fn().mockResolvedValue({}),
  createGrafanaBootstrapSession: vi.fn().mockResolvedValue({}),
}))

describe('GrafanaPage state persistence', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('loads activeTab from localStorage', async () => {
    localStorage.setItem('grafana-active-tab', JSON.stringify('datasources'))
    const { container } = render(<GrafanaPage />)
    // our mock GrafanaTabs outputs data-active attribute
    await waitFor(() => {
      expect(container.querySelector('[data-active]')?.getAttribute('data-active')).toBe('datasources')
    })
  })

  it('persists activeTab changes', async () => {
    const { container } = render(<GrafanaPage />)
    // initially dashboards
    expect(JSON.parse(localStorage.getItem('grafana-active-tab'))).toBe('dashboards')
    // simulate a tab change by writing to storage (component sets via useLocalStorage)
    localStorage.setItem('grafana-active-tab', JSON.stringify('folders'))
    // re-render should reflect new value
    const { container: c2 } = render(<GrafanaPage />)
    await waitFor(() => {
      expect(c2.querySelector('[data-active]')?.getAttribute('data-active')).toBe('folders')
    })
  })
})
