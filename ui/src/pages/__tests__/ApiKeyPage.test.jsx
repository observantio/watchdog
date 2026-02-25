`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, vi, beforeEach } from 'vitest'

vi.mock('../../api', () => ({
  listApiKeys: vi.fn(),
  deleteApiKey: vi.fn(),
  replaceApiKeyShares: vi.fn(),
  getUsers: vi.fn(),
  getGroups: vi.fn(),
}))

const toastMock = { success: vi.fn(), error: vi.fn() }
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => toastMock }))

// provide AuthContext via a mutable user object so tests can update it
let currentUser = { id: 'u2', username: 'me', api_keys: [] }
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ user: currentUser, hasPermission: () => true, updateUser: vi.fn() }) }))

import * as api from '../../api'
import ApiKeyPage from '../ApiKeyPage'

const sharedKey = {
  id: 'k-shared',
  name: 'Shared Key',
  key: 'org-shared',
  otlp_token: null,
  owner_user_id: 'owner-1',
  owner_username: 'alice',
  is_shared: true,
  can_use: true,
  shared_with: [],
  is_default: false,
  is_enabled: true,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: null,
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ApiKeyPage (shared-key UX)', () => {
  it('shows owner username for a shared key', async () => {
    // make the auth context user include the shared key
    vi.mocked(api.listApiKeys).mockResolvedValue([sharedKey])

    // populate auth context user for this test
    currentUser.api_keys = [sharedKey]
    const Page = (await import('../ApiKeyPage')).default

    render(<Page />)

    expect(await screen.findByText(/Shared by alice/i)).toBeInTheDocument()
  })

  it('disables Generate Agent YAML when active key is shared', async () => {
    vi.mocked(api.listApiKeys).mockResolvedValue([sharedKey])
    currentUser.api_keys = [sharedKey]
    const Page = (await import('../ApiKeyPage')).default

    render(<Page />)

    const btn = await screen.findByRole('button', { name: /Generate Agent YAML/i })
    expect(btn).toBeDisabled()
  })

  it('shows permission-specific toast when delete returns 403', async () => {
    // shared key is shown to current user but delete will be forbidden by backend
    vi.mocked(api.listApiKeys).mockResolvedValue([sharedKey])
    vi.mocked(api.deleteApiKey).mockRejectedValue(Object.assign(new Error('Forbidden'), { status: 403, body: { detail: 'Not authorized' } }))

    currentUser.api_keys = [sharedKey]
    const Page = (await import('../ApiKeyPage')).default

    render(<Page />)

    // click row Delete — opens confirm modal
    const rowDelete = await screen.findByRole('button', { name: `Delete ${sharedKey.name}` })
    fireEvent.click(rowDelete)

    // confirm in modal — target the button inside the dialog
    const dialog = await screen.findByRole('dialog')
    const { within } = await import('@testing-library/react')
    const confirmBtn = within(dialog).getByRole('button', { name: 'Delete' })
    fireEvent.click(confirmBtn)

    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('You are not authorized to delete this key'))
  })
})
