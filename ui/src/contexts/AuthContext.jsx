import { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react'
import PropTypes from 'prop-types'
import * as api from '../api'

const AuthContext = createContext(null)
const OIDC_STATE_KEY = 'oidc_state'
const OIDC_NONCE_KEY = 'oidc_nonce'

function syncGrafanaAuthCookie(authToken) {
  if (typeof document === 'undefined') return

  // Cookie auth is server-managed (httpOnly). We only perform best-effort cleanup
  // of a legacy client-managed cookie during logout/migration.
  if (!authToken) {
    document.cookie = 'beobservant_token=; Path=/; Max-Age=0; SameSite=Lax'
  }
}

/**
 * Derive the org_id that should be used for X-Scope-OrgID headers.
 *
 * Priority:
 *   1. The *active* (is_enabled) API key's `key` value — this is the
 *      product/tenant the user has explicitly selected to view.
 *   2. The *default* API key's `key` value — fallback when nothing is enabled.
 *   3. `user.org_id` — ultimate fallback (synced with the default key on the
 *      server; used for Grafana datasource creation and is NOT mutated when
 *      the user merely switches the active key).
 */
function resolveActiveOrgId(userData) {
  const keys = userData?.api_keys || []
  const activeKey = keys.find((k) => k.is_enabled) || keys.find((k) => k.is_default)
  return activeKey?.key || userData?.org_id || ''
}

export function AuthProvider({ children }) {
  const TOKEN_STORAGE_KEY = 'beobservant_access_token'
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(() => {
    try {
      return (typeof localStorage !== 'undefined' && localStorage.getItem(TOKEN_STORAGE_KEY)) || null
    } catch (e) {
      return null
    }
  })
  const [authMode, setAuthMode] = useState({
    provider: 'local',
    oidc_enabled: false,
    password_enabled: true,
    registration_enabled: true,
    oidc_scopes: 'openid profile email',
  })
  const [authModeLoading, setAuthModeLoading] = useState(true)
  const [loading, setLoading] = useState(true)

  const loadAuthMode = useCallback(async () => {
    setAuthModeLoading(true)
    try {
      const mode = await api.getAuthMode()
      setAuthMode(mode)
      return mode
    } catch {
      const fallbackMode = {
        provider: 'local',
        oidc_enabled: false,
        password_enabled: true,
        registration_enabled: true,
        oidc_scopes: 'openid profile email',
      }
      setAuthMode(fallbackMode)
      return fallbackMode
    } finally {
      setAuthModeLoading(false)
    }
  }, [])

  useEffect(() => {
    loadAuthMode()
  }, [loadAuthMode])

  useEffect(() => {
    if (token) {
      api.setAuthToken(token)
    } else {
      api.setAuthToken(null)
    }
  }, [token])

  const loadUser = useCallback(async () => {
    try {
      const userData = await api.getCurrentUser()
      setUser(userData)
      api.setUserOrgIds(resolveActiveOrgId(userData))
    } catch (error) {
      console.error('Failed to load user:', error)
      logout()
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadUser()
  }, [loadUser])

  const login = useCallback(async (username, password, mfa_code) => {
    const response = await api.login(username, password, mfa_code)
    const { access_token } = response
    setToken(access_token)
    try {
      if (typeof localStorage !== 'undefined') localStorage.setItem(TOKEN_STORAGE_KEY, access_token)
    } catch (e) {
      /* ignore storage errors */
    }
    api.setAuthToken(access_token)
    await loadUser()
    return response
  }, [loadUser])

  const startOIDCLogin = useCallback(async () => {
    const state = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
    const nonce = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`

    sessionStorage.setItem(OIDC_STATE_KEY, state)
    sessionStorage.setItem(OIDC_NONCE_KEY, nonce)

    const redirectUri = `${globalThis.location.origin}/#/auth/callback`
    const response = await api.getOIDCAuthorizeUrl(redirectUri, state, nonce)
    if (!response?.authorization_url) {
      throw new Error('OIDC authorization URL was not returned by the server')
    }
    globalThis.location.href = response.authorization_url
  }, [])

  const finishOIDCLogin = useCallback(async ({ code, state }) => {
    const expectedState = sessionStorage.getItem(OIDC_STATE_KEY)
    if (!code) {
      throw new Error('Missing OIDC authorization code')
    }
    if (!state || !expectedState || state !== expectedState) {
      throw new Error('Invalid OIDC state')
    }

    const redirectUri = `${globalThis.location.origin}/#/auth/callback`
    const response = await api.exchangeOIDCCode(code, redirectUri)
    const { access_token } = response || {}
    if (!access_token) {
      throw new Error('OIDC login succeeded but no access token was returned')
    }

    sessionStorage.removeItem(OIDC_STATE_KEY)
    sessionStorage.removeItem(OIDC_NONCE_KEY)

    setToken(access_token)
    try {
      if (typeof localStorage !== 'undefined') localStorage.setItem(TOKEN_STORAGE_KEY, access_token)
    } catch (e) {
      /* ignore storage errors */
    }
    api.setAuthToken(access_token)
    await loadUser()
    return response
  }, [loadUser])

  const register = useCallback(async (username, email, password, fullName) => {
    const response = await api.register(username, email, password, fullName)
    return response
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } catch {
      // best-effort logout; still clear local auth state
    }
    try {
      if (typeof localStorage !== 'undefined') localStorage.removeItem(TOKEN_STORAGE_KEY)
    } catch (e) {
      /* ignore storage errors */
    }
    setToken(null)
    setUser(null)
    api.setAuthToken(null)
    syncGrafanaAuthCookie(null)
  }, [])

  const refreshUser = useCallback(async () => {
    if (token) {
      try {
        const userData = await api.getCurrentUser()
        setUser(userData)
        api.setUserOrgIds(resolveActiveOrgId(userData))
      } catch (error) {
        console.error('Failed to refresh user:', error)
      }
    }
  }, [token])

  const updateUser = useCallback((userData) => {
    setUser(userData)
    api.setUserOrgIds(resolveActiveOrgId(userData))
  }, [])

  const hasPermission = useCallback((permission) => user?.permissions?.includes(permission) || false, [user?.permissions])

  const value = useMemo(() => ({
    user,
    token,
    authMode,
    authModeLoading,
    loading,
    login,
    startOIDCLogin,
    finishOIDCLogin,
    loadAuthMode,
    register,
    logout,
    refreshUser,
    updateUser,
    isAuthenticated: !!token && !!user,
    hasPermission
  }), [user, token, authMode, authModeLoading, loading, login, startOIDCLogin, finishOIDCLogin, loadAuthMode, register, logout, refreshUser, updateUser, hasPermission])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

AuthProvider.propTypes = {
  children: PropTypes.node.isRequired
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
