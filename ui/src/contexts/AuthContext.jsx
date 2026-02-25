import { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import PropTypes from 'prop-types'
import * as api from '../api'

const AuthContext = createContext(null)
const OIDC_STATE_KEY = 'oidc_state'
const OIDC_NONCE_KEY = 'oidc_nonce'
const OIDC_TX_KEY = 'oidc_tx'
const OIDC_CODE_VERIFIER_KEY = 'oidc_code_verifier'

function randomOidcToken(length = 64) {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~'
  if (!globalThis.crypto?.getRandomValues) {
    return `${Date.now()}-${Math.random()}`
  }
  const bytes = new Uint8Array(length)
  globalThis.crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => chars[b % chars.length]).join('')
}

async function pkceChallengeFromVerifier(verifier) {
  if (!globalThis.crypto?.subtle || !globalThis.TextEncoder) return null
  const bytes = new globalThis.TextEncoder().encode(verifier)
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes)
  const hashBytes = Array.from(new Uint8Array(digest), (b) => String.fromCharCode(b)).join('')
  return globalThis.btoa(hashBytes).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

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
  // Token is intentionally kept in-memory only. Authentication is cookie-first
  // (httpOnly, secure). Do NOT persist tokens to localStorage — this removes the
  // attack surface of long-lived tokens in client storage while remaining
  // backward-compatible for API-key flows that set an in-memory token.
  const TOKEN_STORAGE_KEY = null
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(null)
  const [authMode, setAuthMode] = useState({
    provider: 'local',
    oidc_enabled: false,
    password_enabled: true,
    registration_enabled: true,
    oidc_scopes: 'openid profile email',
  })
  const [authModeLoading, setAuthModeLoading] = useState(true)
  const [loading, setLoading] = useState(true)

  const navigate = useNavigate()

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

  // Keep api client in sync with any in-memory token (API-key flows).
  // For cookie-based sessions 'token' will normally be null and the browser
  // will send the httpOnly session cookie automatically with requests.
  useEffect(() => {
    api.setAuthToken(token || null)
  }, [token])

  const loadUser = useCallback(async () => {
    try {
      // Use a non-redirecting /me call during initial app startup so a
      // transient 401 or network error does not instantly navigate the
      // user away or clear server-managed session cookies.
      const userData = await api.getCurrentUserNoRedirect()
      setUser(userData)
      api.setUserOrgIds(resolveActiveOrgId(userData))
    } catch (error) {
      // Do NOT call logout() here — if /me fails we simply treat the user
      // as unauthenticated and let the UI remain in-place (avoids flashing
      // the login screen on reload). Callers can use `logout()` explicitly.
      console.debug('AuthProvider: initial user load failed (treating as unauthenticated):', error?.message || error)
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadUser()
  }, [loadUser])

  // Always attempt to refresh user details from the server. In cookie-based
  // sessions there will be no in-memory token, but the browser will send the
  // httpOnly cookie with the request; treat a successful /me call as proof of
  // authentication.
  const refreshUser = useCallback(async () => {
    try {
      const userData = await api.getCurrentUser()
      setUser(userData)
      api.setUserOrgIds(resolveActiveOrgId(userData))
    } catch (error) {
      // Ignore failures here; caller can decide to log out or show UI.
      console.error('Failed to refresh user:', error)
      setUser(null)
    }
  }, [])

  const login = useCallback(async (username, password, mfa_code) => {
    // The server SHOULD set an httpOnly session cookie on successful login.
    // If it additionally returns an access_token we accept it as an in-memory
    // fallback (useful for API-key or non-cookie environments), but we NEVER
    // persist tokens to localStorage.
    const response = await api.login(username, password, mfa_code)
    const { access_token } = response || {}

    // keep token in-memory only (no localStorage)
    setToken(access_token || null)

    // api client follows the in-memory token (if any)
    api.setAuthToken(access_token || null)

    // Always refresh user state from server (cookie-based or token-based).
    // Use `refreshUser()` here so a returned `access_token` (in-memory)
    // is used via the Authorization header if present. This fixes a race
    // where `/api/auth/login` returns a token but the cookie isn't set —
    // `getCurrentUser()` will succeed using the in-memory token.
    await refreshUser()
    return response
  }, [refreshUser])

  const startOIDCLogin = useCallback(async () => {
    const state = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
    const nonce = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
    const codeVerifier = randomOidcToken(96)
    const codeChallenge = await pkceChallengeFromVerifier(codeVerifier)

    sessionStorage.setItem(OIDC_STATE_KEY, state)
    sessionStorage.setItem(OIDC_NONCE_KEY, nonce)
    sessionStorage.setItem(OIDC_CODE_VERIFIER_KEY, codeVerifier)

    const redirectUri = `${globalThis.location.origin}/#/auth/callback`
    const response = await api.getOIDCAuthorizeUrl(redirectUri, {
      state,
      nonce,
      code_challenge: codeChallenge,
      code_challenge_method: codeChallenge ? 'S256' : null,
    })
    if (!response?.authorization_url) {
      throw new Error('OIDC authorization URL was not returned by the server')
    }
    if (!response?.transaction_id) {
      throw new Error('OIDC transaction was not returned by the server')
    }
    sessionStorage.setItem(OIDC_TX_KEY, response.transaction_id)
    if (response?.state) {
      sessionStorage.setItem(OIDC_STATE_KEY, response.state)
    }
    globalThis.location.href = response.authorization_url
  }, [])

  const finishOIDCLogin = useCallback(async ({ code, state }) => {
    const expectedState = sessionStorage.getItem(OIDC_STATE_KEY)
    const transactionId = sessionStorage.getItem(OIDC_TX_KEY)
    const codeVerifier = sessionStorage.getItem(OIDC_CODE_VERIFIER_KEY)
    if (!code) {
      throw new Error('Missing OIDC authorization code')
    }
    if (!state || !expectedState || state !== expectedState) {
      throw new Error('Invalid OIDC state')
    }
    if (!transactionId) {
      throw new Error('Missing OIDC transaction')
    }

    const redirectUri = `${globalThis.location.origin}/#/auth/callback`
    const response = await api.exchangeOIDCCode(code, redirectUri, {
      state,
      transaction_id: transactionId,
      code_verifier: codeVerifier,
    })
    const { access_token } = response || {}

    sessionStorage.removeItem(OIDC_STATE_KEY)
    sessionStorage.removeItem(OIDC_NONCE_KEY)
    sessionStorage.removeItem(OIDC_TX_KEY)
    sessionStorage.removeItem(OIDC_CODE_VERIFIER_KEY)

    // prefer cookie-based session; accept access_token as in-memory fallback
    setToken(access_token || null)
    api.setAuthToken(access_token || null)
    await loadUser()
    return response
  }, [loadUser])

  const register = useCallback(async (username, email, password, fullName) => {
    const response = await api.register(username, email, password, fullName)
    return response
  }, [])

  const logout = useCallback(async () => {
    try {
      // Server should clear the httpOnly cookie and invalidate the session.
      await api.logout()
    } catch {
      // best-effort logout; still clear client state
    }
    setToken(null)
    setUser(null)
    api.setAuthToken(null)
    syncGrafanaAuthCookie(null)
    sessionStorage.removeItem(OIDC_STATE_KEY)
    sessionStorage.removeItem(OIDC_NONCE_KEY)
    sessionStorage.removeItem(OIDC_TX_KEY)
    sessionStorage.removeItem(OIDC_CODE_VERIFIER_KEY)
  }, [])

  const updateUser = useCallback((userData) => {
    setUser(userData)
    api.setUserOrgIds(resolveActiveOrgId(userData))
  }, [])

  // helper to clear all local authentication state without calling the
  // server. Used when a request returns 401 (expired session) so the UI can
  // immediately hide protected content and redirect to the login page.
  const clearSession = useCallback(() => {
    setToken(null)
    setUser(null)
    api.setAuthToken(null)
    syncGrafanaAuthCookie(null)
    sessionStorage.removeItem(OIDC_STATE_KEY)
    sessionStorage.removeItem(OIDC_NONCE_KEY)
    sessionStorage.removeItem(OIDC_TX_KEY)
    sessionStorage.removeItem(OIDC_CODE_VERIFIER_KEY)
  }, [])

  const hasPermission = useCallback((permission) => user?.permissions?.includes(permission) || false, [user?.permissions])

  const value = useMemo(() => ({
    user,
    // token is intentionally in-memory only and may be null for cookie sessions
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
    // Authentication is determined by the server-provided `user` object
    isAuthenticated: !!user,
    hasPermission
  }), [user, token, authMode, authModeLoading, loading, login, startOIDCLogin, finishOIDCLogin, loadAuthMode, register, logout, refreshUser, updateUser, hasPermission])

  // automatically logout when any API call reports a 401 status. we
  // listen for both the generic "api-error" event (which already fires)
  // and our specific "session-expired" event emitted by the request helper.
  useEffect(() => {
    const handler = (e) => {
      const status = e?.detail?.status
      if (status === 401) {
        clearSession()
        // navigate after clearing state; login page hides header via
        // isAuthenticated check in AppContent
        navigate('/login')
      }
    }
    globalThis.addEventListener('api-error', handler)
    globalThis.addEventListener('session-expired', handler)
    return () => {
      globalThis.removeEventListener('api-error', handler)
      globalThis.removeEventListener('session-expired', handler)
    }
  }, [clearSession, navigate])

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
