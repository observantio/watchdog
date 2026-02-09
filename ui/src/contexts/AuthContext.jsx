import { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react'
import PropTypes from 'prop-types'
import * as api from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(localStorage.getItem('auth_token'))
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (token) {
      api.setAuthToken(token)
      loadUser()
    } else {
      setLoading(false)
    }
  }, [token])

  const loadUser = useCallback(async () => {
    try {
      const userData = await api.getCurrentUser()
      setUser(userData)
      const enabledKeys = (userData.api_keys || []).filter((k) => k.is_enabled).map((k) => k.key)
      api.setUserOrgIds(enabledKeys?.length > 0 ? enabledKeys : [userData.org_id || 'default'])
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
  }, [])

  const refreshUser = useCallback(async () => {
    if (token) {
      try {
        const userData = await api.getCurrentUser()
        setUser(userData)
        const enabledKeys = (userData.api_keys || []).filter((k) => k.is_enabled).map((k) => k.key)
        api.setUserOrgIds(enabledKeys?.length > 0 ? enabledKeys : [userData.org_id || 'default'])
      } catch (error) {
        console.error('Failed to refresh user:', error)
      }
    }
  }, [token])

  const updateUser = useCallback((userData) => {
    setUser(userData)
    const enabledKeys = (userData.api_keys || []).filter((k) => k.is_enabled).map((k) => k.key)
    api.setUserOrgIds(enabledKeys?.length > 0 ? enabledKeys : [userData.org_id || 'default'])
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
