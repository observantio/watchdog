import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, vi, beforeEach } from 'vitest'

vi.mock('../../api', () => ({
  enrollMFA: vi.fn(),
  verifyMFA: vi.fn(),
  clearSetupToken: vi.fn(),
}))

vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))

// mock auth context so the page shows password login
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    login: vi.fn().mockRejectedValue({ status: 401, body: { detail: { mfa_setup_required: true, setup_token: 'setup-1' } } }),
    startOIDCLogin: vi.fn(),
    authMode: { oidc_enabled: false, password_enabled: true },
    authModeLoading: false,
    isAuthenticated: false,
    loading: false,
  })
}))

// react-router hooks used by LoginPage; mock navigate to avoid Router in tests
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }))

import * as api from '../../api'
import LoginPage from '../LoginPage'

describe('LoginPage MFA setup flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('allows enrolling and copying recovery codes', async () => {
    api.enrollMFA.mockResolvedValue({ secret: 's', otpauth_url: 'otpauth://', })
    api.verifyMFA.mockResolvedValue({ recovery_codes: ['r1', 'r2'] })

    // mock clipboard
    const write = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText: write } })

    render(<LoginPage />)

    // fill login form and submit — our mocked login will trigger MFA setup required
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    // after login rejection we should see MFA setup UI
    await waitFor(() => expect(screen.getByText(/Set up two-factor authentication/i)).toBeInTheDocument())

    // start setup
    fireEvent.click(screen.getByRole('button', { name: /Start MFA setup/i }))

    // verify step 1 -> enter code and verify
    await waitFor(() => expect(screen.getByLabelText(/Authentication code/i)).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText(/Authentication code/i), { target: { value: '123456' } })
    fireEvent.click(screen.getByRole('button', { name: /Verify/i }))

    // now recovery codes should be visible
    await waitFor(() => expect(screen.getByText(/Recovery codes — save these now/i)).toBeInTheDocument())

    // click Copy codes — should call clipboard
    fireEvent.click(screen.getByRole('button', { name: /Copy codes/i }))
    await waitFor(() => expect(write).toHaveBeenCalled())
  })
})
