`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, vi, beforeEach } from 'vitest'

const loginMock = vi.fn()

vi.mock('../../api', () => ({
  enrollMFA: vi.fn(),
  verifyMFA: vi.fn(),
  clearSetupToken: vi.fn(),
  setSetupToken: vi.fn(),
}))

vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    login: loginMock,
    startOIDCLogin: vi.fn(),
    authMode: { oidc_enabled: false, password_enabled: true },
    authModeLoading: false,
    isAuthenticated: false,
    loading: false,
  }),
}))

vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }))

import LoginPage from '../LoginPage'

describe('LoginPage MFA recovery toggle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    loginMock
      .mockRejectedValueOnce({ status: 401, body: { detail: 'MFA required' } })
      .mockResolvedValueOnce({ access_token: 'token-1' })
  })

  it('allows switching to recovery code mode during MFA challenge', async () => {
    render(<LoginPage />)

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(screen.getByLabelText(/Authentication code/i)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /Use recovery code instead/i }))
    expect(screen.getByLabelText(/Recovery code/i)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/Recovery code/i), { target: { value: 'recovery-1' } })
    fireEvent.click(screen.getByRole('button', { name: /Verify/i }))

    await waitFor(() => expect(loginMock).toHaveBeenLastCalledWith('alice', 'pw', 'recovery-1'))
  })
})

