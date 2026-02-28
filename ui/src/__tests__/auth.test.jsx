import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth, computeOidcRedirectUri } from '../contexts/AuthContext'
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
  const renderWithRouter = (node) =>
    render(
      <MemoryRouter initialEntries={['/']}>
        {node}
      </MemoryRouter>
    )

  it('loads user from cookie-based session (no access_token)', async () => {
    api.getCurrentUserNoRedirect.mockResolvedValue({ username: 'alice', org_id: 'org-a' })

    renderWithRouter(
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

    renderWithRouter(
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

    renderWithRouter(
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

    renderWithRouter(
      <AuthProvider>
        <Caller />
      </AuthProvider>
    )

    await waitFor(() => expect(api.getCurrentUser).toHaveBeenCalled())
  })

  it('logs out and navigates to /login when a 401 api-error event occurs', async () => {
    // initial user load succeeds
    api.getCurrentUserNoRedirect.mockResolvedValue({ username: 'joe' })
    api.getCurrentUser.mockResolvedValue({ username: 'joe' })

    function Check() {
      const { user, isAuthenticated } = useAuth()
      const location = useLocation()
      return (
        <>
          <span data-testid="auth">{String(isAuthenticated)}</span>
          <span data-testid="loc">{location.pathname}</span>
        </>
      )
    }

    renderWithRouter(
      <AuthProvider>
        <Check />
      </AuthProvider>
    )

    // wait for login/user state to be set
    await waitFor(() => expect(screen.getByTestId('auth').textContent).toBe('true'))

    // fire the api-error event as if server returned 401
    act(() => {
      globalThis.window.dispatchEvent(new CustomEvent('api-error', { detail: { status: 401, body: {} } }))
    })

    // after handler runs, user should be unauthenticated and location changes
    await waitFor(() => {
      expect(screen.getByTestId('auth').textContent).toBe('false')
      expect(screen.getByTestId('loc').textContent).toBe('/login')
    })
  })
})
