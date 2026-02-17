import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { AuthProvider, useAuth } from '../contexts/AuthContext'
import * as api from '../api'

vi.mock('../api')

afterEach(() => {
  vi.restoreAllMocks()
})

function Status() {
  const { user, isAuthenticated } = useAuth()
  return (
    <div>
      <span data-testid="auth">{String(isAuthenticated)}</span>
      <span data-testid="user">{user ? user.username : 'null'}</span>
    </div>
  )
}

describe('AuthContext cookie-first behavior', () => {
  it('loads user from cookie-based session (no access_token)', async () => {
    api.getCurrentUserNoRedirect.mockResolvedValue({ username: 'alice', org_id: 'org-a' })

    render(
      <AuthProvider>
        <Status />
      </AuthProvider>
    )

    await waitFor(() => expect(screen.getByTestId('auth').textContent).toBe('true'))
    expect(screen.getByTestId('user').textContent).toBe('alice')
  })

  it('login (cookie response) does not persist token to localStorage and loads user', async () => {
    api.login.mockResolvedValue({})
    api.getCurrentUserNoRedirect.mockRejectedValue(new Error('Unauthenticated'))
    api.getCurrentUser.mockResolvedValue({ username: 'bob' })

    const spySet = vi.spyOn(globalThis.localStorage.__proto__, 'setItem')

    function LoginCaller() {
      const { login } = useAuth()
      React.useEffect(() => {
        login('u', 'p')
      }, [login])
      return null
    }

    render(
      <AuthProvider>
        <LoginCaller />
        <Status />
      </AuthProvider>
    )

    await waitFor(() => expect(screen.getByTestId('user').textContent).toBe('bob'))
    expect(spySet).not.toHaveBeenCalled()
    expect(api.getCurrentUser).toHaveBeenCalled()
  })

  it('login (access_token returned) keeps token in-memory and does NOT write localStorage', async () => {
    api.login.mockResolvedValue({ access_token: 'tok-123' })
    api.getCurrentUserNoRedirect.mockRejectedValue(new Error('Unauthenticated'))
    api.getCurrentUser.mockResolvedValue({ username: 'charlie' })
    const spySet = vi.spyOn(globalThis.localStorage.__proto__, 'setItem')
    const spySetAuth = vi.spyOn(api, 'setAuthToken')

    function LoginCaller() {
      const { login } = useAuth()
      React.useEffect(() => {
        login('u', 'p')
      }, [login])
      return null
    }

    render(
      <AuthProvider>
        <LoginCaller />
        <Status />
      </AuthProvider>
    )

    await waitFor(() => expect(screen.getByTestId('user').textContent).toBe('charlie'))
    expect(spySet).not.toHaveBeenCalled()
    expect(spySetAuth).toHaveBeenCalledWith('tok-123')
    expect(api.getCurrentUser).toHaveBeenCalled()
    expect(api.getCurrentUserNoRedirect).toHaveBeenCalled()
  })

  it('refreshUser calls getCurrentUser even when in-memory token is null', async () => {
    api.getCurrentUserNoRedirect.mockResolvedValue({ username: 'seed' })
    api.getCurrentUser.mockResolvedValue({ username: 'dave' })

    function Caller() {
      const { refreshUser } = useAuth()
      React.useEffect(() => {
        refreshUser()
      }, [refreshUser])
      return <Status />
    }

    render(
      <AuthProvider>
        <Caller />
      </AuthProvider>
    )

    await waitFor(() => expect(api.getCurrentUser).toHaveBeenCalled())
  })
})
