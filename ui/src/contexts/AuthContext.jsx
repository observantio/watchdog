import { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react'
import PropTypes from 'prop-types'
import * as api from '../api'

const AuthContext = createContext(null)

function syncGrafanaAuthCookie(authToken) {
  if (typeof document === 'undefined') return

  if (!authToken) {
    document.cookie = 'beobservant_token=; Path=/; Max-Age=0; SameSite=Lax'
    return
  }

  document.cookie = `beobservant_token=${encodeURIComponent(authToken)}; Path=/; Max-Age=86400; SameSite=Lax`
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
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(localStorage.getItem('auth_token'))
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (token) {
      api.setAuthToken(token)
      syncGrafanaAuthCookie(token)
      loadUser()
    } else {
      syncGrafanaAuthCookie(null)
      setLoading(false)
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

  const login = useCallback(async (username, password) => {
    const response = await api.login(username, password)
    const { access_token } = response
    localStorage.setItem('auth_token', access_token)
    setToken(access_token)
    api.setAuthToken(access_token)
    syncGrafanaAuthCookie(access_token)
    await loadUser()
    return response
  }, [loadUser])

  const register = useCallback(async (username, email, password, fullName) => {
    const response = await api.register(username, email, password, fullName)
    return response
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('auth_token')
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
    loading,
    login,
    register,
    logout,
    refreshUser,
    updateUser,
    isAuthenticated: !!token && !!user,
    hasPermission
  }), [user, token, loading, login, register, logout, refreshUser, updateUser, hasPermission])

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
