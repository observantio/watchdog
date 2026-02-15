import { NavLink, useNavigate } from 'react-router-dom'
import { useState, useRef, useEffect, useCallback } from 'react'
import { useAuth } from '../contexts/AuthContext'
import PropTypes from 'prop-types'
import ThemeToggle from './ThemeToggle'
import { Badge } from './ui'
import ChangePasswordModal from './ChangePasswordModal'
import * as api from '../api'
import { NAV_ITEMS } from '../utils/constants'

const NAV_ITEM_LIST = Object.values(NAV_ITEMS)

function NavItem({ item, isMobile = false }) {
  const baseClasses = isMobile
    ? 'rounded-lg text-xs font-medium whitespace-nowrap flex items-center gap-2 transition-all px-3 py-1.5'
    : 'px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-2'

  return (
    <NavLink
      to={item.path}
      className={({ isActive }) =>
        `${baseClasses} ${
          isActive
            ? 'bg-sre-primary/10 text-sre-primary shadow-glow-sm'
            : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
        }`
      }
    >
      <span className="material-icons text-sm leading-none" aria-hidden>{item.icon}</span>
      {' '}{item.label}
    </NavLink>
  )
}

NavItem.propTypes = {
  item: PropTypes.shape({
    label: PropTypes.string.isRequired,
    icon: PropTypes.string.isRequired,
    path: PropTypes.string.isRequired,
  }).isRequired,
  isMobile: PropTypes.bool,
}

function ApiKeyDropdown({ apiKeys, activeKeyId, onSelect, disabled, compact = false }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('click', onClick)
    return () => document.removeEventListener('click', onClick)
  }, [])

  const selectedKey = apiKeys?.find(k => k.id === activeKeyId)
  const btnClass = compact
    ? 'px-2 py-1 text-xs bg-sre-surface border border-sre-border rounded text-sre-text flex items-center justify-between'
    : 'px-3 py-2 min-w-[190px] text-xs bg-sre-surface border border-sre-border rounded text-sre-text flex items-center justify-between'

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        disabled={disabled}
        className={btnClass}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="truncate" style={{ maxWidth: '70px' }}>{selectedKey?.name || (compact ? 'Select' : 'Select API Key')}</span>
        <svg className={`${compact ? 'w-3 h-3' : 'w-4 h-4'} text-sre-text-muted`} viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 011.08 1.04l-4.25 4.25a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z" clipRule="evenodd" />
        </svg>
      </button>
      {open && (
        <ul
          role="listbox"
          className="absolute top-full mt-1 w-full bg-sre-bg-card border border-sre-border rounded shadow-lg z-50 py-1 max-h-60 overflow-y-auto"
        >
          {apiKeys.map((k) => (
            <li key={k.id} role="option" aria-selected={k.id === activeKeyId}>
              <button
                type="button"
                onClick={() => {
                  onSelect(k.id)
                  setOpen(false)
                }}
                className={`w-full text-left ${compact ? 'px-2 py-1' : 'px-3 py-2'} text-xs text-sre-text hover:bg-sre-surface/50`}
              >
                <span className="truncate block" style={{ maxWidth: '70px' }}>{k.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

ApiKeyDropdown.propTypes = {
  apiKeys: PropTypes.array.isRequired,
  activeKeyId: PropTypes.string,
  onSelect: PropTypes.func.isRequired,
  disabled: PropTypes.bool,
  compact: PropTypes.bool,
}

export default function Header() {
  const { user, logout, hasPermission, refreshUser } = useAuth()
  const [showChangePassword, setShowChangePassword] = useState(false)
  const [activeKeyId, setActiveKeyId] = useState('')
  const [switchingKey, setSwitchingKey] = useState(false)

  useEffect(() => {
    if (!user?.api_keys?.length) {
      setActiveKeyId('')
      return
    }
    const enabledKey = user.api_keys.find((k) => k.is_enabled)
    setActiveKeyId(enabledKey?.id || '')
  }, [user])

  const handleActiveKeyChange = useCallback(async (nextId) => {
    if (!nextId || nextId === activeKeyId) return
    setActiveKeyId(nextId)
    setSwitchingKey(true)
    try {
      await api.updateApiKey(nextId, { is_enabled: true })
      await refreshUser()
    } catch (err) {
      await refreshUser()
    } finally {
      setSwitchingKey(false)
    }
  }, [activeKeyId, refreshUser])

  const visibleNavItems = NAV_ITEM_LIST.filter(
    item => !item.permission || hasPermission(item.permission)
  )

  return (
    <header className="sticky top-0 z-50 bg-sre-surface/80 backdrop-blur-xl border-b border-sre-border shadow-lg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <div className="w-10 h-10 rounded-lg flex items-center">
                <svg className="w-6 h-6 text-sre-primary eye-blink" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12zm11 3a3 3 0 100-6 3 3 0 000 6z" />
                </svg>
              </div>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-1" aria-label="Main navigation">
            {visibleNavItems.map(item => (
              <NavItem key={item.path} item={item} />
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <ThemeToggle />

            {user?.api_keys?.length > 0 && (
              <div className="hidden sm:flex items-center gap-2">
                <ApiKeyDropdown
                  apiKeys={user.api_keys}
                  activeKeyId={activeKeyId}
                  onSelect={handleActiveKeyChange}
                  disabled={switchingKey}
                />
              </div>
            )}

            <div className="relative">
              <UserMenu
                user={user}
                logout={logout}
                hasPermission={hasPermission}
                openChangePassword={() => setShowChangePassword(true)}
              />
              <ChangePasswordModal
                isOpen={showChangePassword}
                onClose={() => setShowChangePassword(false)}
                userId={user?.id}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Mobile Navigation */}
      <div className="md:hidden border-t border-sre-border px-4 py-2 flex gap-2 overflow-x-auto">
        {visibleNavItems.map(item => (
          <NavItem key={item.path} item={item} isMobile />
        ))}
        {user?.api_keys?.length > 0 && (
          <div className="flex items-center gap-2 ml-auto">
            <ApiKeyDropdown
              apiKeys={user.api_keys}
              activeKeyId={activeKeyId}
              onSelect={handleActiveKeyChange}
              disabled={switchingKey}
              compact
            />
          </div>
        )}
      </div>
    </header>
  )
}

function UserMenu({ user, logout, hasPermission, openChangePassword }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const menuRef = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('click', onClick)
    return () => document.removeEventListener('click', onClick)
  }, [])

  useEffect(() => {
    if (open) {
      setTimeout(() => menuRef.current?.focus(), 0)
    }
  }, [open])

  const handleLogout = () => {
    setOpen(false)
    logout()
    navigate('/login')
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-sre-surface-light"
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={`User menu for ${user?.username || 'user'}`}
      >
        <Badge variant={user?.role === 'admin' ? 'error' : 'info'}>{user?.role || 'user'}</Badge>
        <span className="hidden sm:block text-sre-text text-sm">{user?.username ? (user.username.length > 6 ? user.username.slice(0, 6) + '...' : user.username) : ''}</span>
        <svg className="w-4 h-4 text-sre-text-muted" viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 011.08 1.04l-4.25 4.25a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z" clipRule="evenodd" />
        </svg>
      </button>

      {open && (
        <div
          ref={menuRef}
          tabIndex={-1}
          onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false) }}
          role="menu"
          className="absolute right-0 mt-2 w-44 bg-sre-bg-card border border-sre-border rounded shadow-lg z-50 py-1"
        >
          {hasPermission('manage:users') && (
            <NavLink to="/users" role="menuitem" tabIndex={0} className="block px-3 py-2 text-sm text-sre-text hover:bg-sre-surface/50" onClick={() => setOpen(false)}>
              <span className="material-icons text-sm leading-none align-middle mr-2 text-sre-text-muted" aria-hidden>people</span>{' '}Users
            </NavLink>
          )}
          {hasPermission('manage:groups') && (
            <NavLink to="/groups" role="menuitem" tabIndex={0} className="block px-3 py-2 text-sm text-sre-text hover:bg-sre-surface/50" onClick={() => setOpen(false)}>
              <span className="material-icons text-sm leading-none align-middle mr-2 text-sre-text-muted" aria-hidden>groups</span>{' '}Groups
            </NavLink>
          )}

          <div className="border-t border-sre-border my-1" />

          <NavLink to="/apikey" role="menuitem" tabIndex={0} className="block px-3 py-2 text-sm text-sre-text hover:bg-sre-surface/50" onClick={() => setOpen(false)}>
            <span className="material-icons text-sm leading-none align-middle mr-2 text-sre-text-muted" aria-hidden>key</span>{' '}API Key
          </NavLink>

          <NavLink to="/integrations" role="menuitem" tabIndex={0} className="block px-3 py-2 text-sm text-sre-text hover:bg-sre-surface/50" onClick={() => setOpen(false)}>
            <span className="material-icons text-sm leading-none align-middle mr-2 text-sre-text-muted" aria-hidden>integration_instructions</span>{' '}Integrations
          </NavLink>

          <button type="button" role="menuitem" onClick={() => { setOpen(false); openChangePassword?.() }} className="w-full text-left px-3 py-2 text-sm text-sre-text hover:bg-sre-surface/50">
            <span className="material-icons text-sm leading-none align-middle mr-2 text-sre-text-muted" aria-hidden>lock</span>{' '}Password
          </button>

          <button type="button" role="menuitem" onClick={handleLogout} className="w-full text-left px-3 py-2 text-sm text-sre-text hover:bg-sre-surface/50">
            <span className="material-icons text-sm leading-none align-middle mr-2 text-sre-text-muted" aria-hidden>logout</span>{' '}Logout
          </button>
        </div>
      )}
    </div>
  )
}

UserMenu.propTypes = {
  user: PropTypes.object,
  logout: PropTypes.func.isRequired,
  hasPermission: PropTypes.func.isRequired,
  openChangePassword: PropTypes.func,
}
