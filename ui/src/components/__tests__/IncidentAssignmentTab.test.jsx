import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import IncidentAssignmentTab from '../IncidentAssignmentTab'

describe('IncidentAssignmentTab', () => {
  it('calls onAssign when a user or "Unassigned" is clicked', () => {
    const setAssigneeSearch = vi.fn()
    const setIncidentDrafts = vi.fn()

    const activeIncident = { id: 'i1', assignee: '' }
    const activeIncidentDraft = { assignee: '' }
    const users = [ { id: 'u1', username: 'alice', email: 'a@example.com' } ]

    render(
      <IncidentAssignmentTab
        canReadUsers
        assigneeSearch=""
        setAssigneeSearch={setAssigneeSearch}
        activeIncident={activeIncident}
        activeIncidentDraft={activeIncidentDraft}
        setIncidentDrafts={setIncidentDrafts}
        filteredIncidentUsers={users}
        getUserLabel={(u) => `${u.username}${u.email ? ` ${u.email}` : ''}`}
      />
    )

    // click user -> should call setIncidentDrafts updater
    const userBtn = screen.getByText('alice a@example.com')
    fireEvent.click(userBtn)
    expect(setIncidentDrafts).toHaveBeenCalled()
    const userUpdater = setIncidentDrafts.mock.calls[0][0]
    expect(typeof userUpdater).toBe('function')
    expect(userUpdater({})).toEqual({ i1: { assignee: 'u1' } })

    // click Unassigned -> should call setIncidentDrafts updater with empty assignee
    const unassignedBtn = screen.getByText('Unassigned')
    fireEvent.click(unassignedBtn)
    const unassignedUpdater = setIncidentDrafts.mock.calls[1][0]
    expect(typeof unassignedUpdater).toBe('function')
    expect(unassignedUpdater({})).toEqual({ i1: { assignee: '' } })
  })

  it('shows permission message when cannot read users', () => {
    render(
      <IncidentAssignmentTab
        canReadUsers={false}
        assigneeSearch=""
        setAssigneeSearch={() => {}}
        activeIncident={{ id: 'i1' }}
        activeIncidentDraft={{}}
        setIncidentDrafts={() => {}}
        filteredIncidentUsers={[]}
        getUserLabel={() => ''}
        onAssign={() => {}}
      />
    )

    expect(screen.getByText(/You do not have permission to list users/i)).toBeInTheDocument()
  })
})
