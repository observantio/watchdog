import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent, screen, within } from '@testing-library/react'
import { axe, toHaveNoViolations } from 'jest-axe'
import CreateUserModal from '../CreateUserModal'

expect.extend(toHaveNoViolations)

vi.mock('../../../contexts/ToastContext', () => ({
  useToast: vi.fn(() => ({ success: vi.fn(), error: vi.fn() })),
}))
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: vi.fn(() => ({ authMode: { oidc_enabled: false, password_enabled: true } })),
}))

describe('CreateUserModal — accessibility & keyboard interactions', () => {
  it('toggles group selection with Enter/Space and has no a11y violations', async () => {
    const groups = [ { id: 'g1', name: 'Group One' }, { id: 'g2', name: 'Group Two' } ]
    const { container } = render(
      <CreateUserModal isOpen onClose={() => {}} onCreated={() => {}} groups={groups} users={[]} />
    )

    // find the group card by visible name and locate the role=checkbox wrapper
    const labelEl = screen.getByText('Group One')
    const card = labelEl.closest('[role="checkbox"]')
    expect(card).toBeInTheDocument()
    expect(card).toHaveAttribute('tabindex')

    // checkbox inside the card should start unchecked
    const innerCheckbox = within(card).getByRole('checkbox')
    expect(innerCheckbox).not.toBeChecked()

    // press Enter to toggle
    card.focus()
    fireEvent.keyDown(card, { key: 'Enter', code: 'Enter', charCode: 13 })
    expect(innerCheckbox).toBeChecked()

    // press Space to toggle off
    fireEvent.keyDown(card, { key: ' ', code: 'Space', charCode: 32 })
    expect(innerCheckbox).not.toBeChecked()

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})