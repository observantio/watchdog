import React from 'react'
import { render, fireEvent, waitFor, screen } from '@testing-library/react'
import { vi, describe, it, beforeEach, expect } from 'vitest'

vi.mock('../../components/ui', () => ({
  Card: ({ children }) => <div>{children}</div>,
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Select: ({ children, ...props }) => <select {...props}>{children}</select>,
  Badge: ({ children }) => <span>{children}</span>,
  Spinner: () => <div>Loading</div>,
  Modal: ({ children, isOpen }) => (isOpen ? <div>{children}</div> : null),
  Input: (props) => <input {...props} />,
  Alert: ({ children }) => <div>{children}</div>,
}))
vi.mock('../../components/HelpTooltip', () => ({ default: () => <span /> }))
vi.mock('../../components/ui/PageHeader', () => ({ default: ({ children }) => <div>{children}</div> }))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 'u2', username: 'alice' }, hasPermission: () => true }) }))

vi.mock('../../api', () => ({
  getIncidents: vi.fn(),
  updateIncident: vi.fn(),
  getUsers: vi.fn(),
  getGroups: vi.fn(),
  listJiraIntegrations: vi.fn(),
  listJiraProjectsByIntegration: vi.fn(),
  listJiraIssueTypes: vi.fn(),
  listIncidentJiraComments: vi.fn(),
  createIncidentJira: vi.fn(),
  createIncidentJiraComment: vi.fn(),
  syncIncidentJiraComments: vi.fn(),
  getAlertsByFilter: vi.fn(),
}))

import IncidentBoardPage, { clearDroppedState } from '../IncidentBoardPage'
import * as api from '../../api'

describe('clearDroppedState', () => {
  it('removes dropped id key when id is defined', () => {
    const prev = { a: true, b: true }
    const next = clearDroppedState(prev, 'a')

    expect(next).toEqual({ b: true })
    expect(prev).toEqual({ a: true, b: true })
  })

  it('returns previous state when dropped id is undefined', () => {
    const prev = { a: true }
    const next = clearDroppedState(prev, undefined)

    expect(next).toBe(prev)
  })

  it('returns previous state when dropped id is empty', () => {
    const prev = { a: true }
    const next = clearDroppedState(prev, '')

    expect(next).toBe(prev)
  })
})

describe('IncidentBoardPage — UI refresh & persistence', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('refreshes incidents after saving assignment (no reload needed)', async () => {
    const initial = { id: 'i1', alertName: 'Alert 1', status: 'open', assignee: '', fingerprint: 'f1', lastSeenAt: new Date().toISOString(), severity: 'warning', notes: [] }
    const updated = { ...initial, assignee: 'u2' }
    const user = { id: 'u2', username: 'alice', email: 'alice@example.com' }

    api.getIncidents.mockResolvedValueOnce([initial]) // initial load
    api.getUsers.mockResolvedValue([user])
    api.getGroups.mockResolvedValue([])
    api.updateIncident.mockResolvedValue(updated)
    api.getIncidents.mockResolvedValueOnce([updated]) // after refresh

    const { getByText, findByText, getByTitle } = render(<IncidentBoardPage />)

    // initial incident visible
    await findByText('Alert 1')

    // open modal (use the View notes button which includes the title)
    const viewNotesBtn = getByTitle('View notes')
    fireEvent.click(viewNotesBtn)

    // switch to Assignment tab and 'Assign to me' (useAuth user is u2)
    fireEvent.click(getByText('Assignment'))
    fireEvent.click(getByText('Assign to me'))

    // save changes
    fireEvent.click(getByText('Save changes'))

    await waitFor(() => expect(api.updateIncident).toHaveBeenCalledWith('i1', expect.objectContaining({ assignee: 'u2' })))

    // after refresh, the assignee label should render the username
    await waitFor(() => expect(getByText('alice')).toBeTruthy())
  })

  it('persists visibility tab and selected group to localStorage', async () => {
    api.getIncidents.mockResolvedValue([])
    api.getGroups.mockResolvedValue([{ id: 'g1', name: 'Team A' }])

    const { getByText, getByRole } = render(<IncidentBoardPage />)

    // switch to Group tab
    fireEvent.click(getByText('Group'))

    // select the group
    const select = getByRole('combobox')
    fireEvent.change(select, { target: { value: 'g1' } })

    // localStorage should now contain our persisted values
    expect(localStorage.getItem('incidents-visibility')).toEqual(JSON.stringify('group'))
    expect(localStorage.getItem('incidents-selected-group')).toEqual(JSON.stringify('g1'))
  })
})
