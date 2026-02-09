import { NavLink, useNavigate } from 'react-router-dom'
import { useState, useRef, useEffect } from 'react'
import { useAuth } from '../contexts/AuthContext'
import PropTypes from 'prop-types'
import ThemeToggle from './ThemeToggle'
import { Badge } from './ui'
import ChangePasswordModal from './ChangePasswordModal'

export default function Header() {
  const { user, logout, hasPermission } = useAuth()
  const [showChangePassword, setShowChangePassword] = useState(false)

  return (
    <header className="sticky top-0 z-50 bg-sre-surface/80 backdrop-blur-xl border-b border-sre-border shadow-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg flex items-center justify-center">
                  <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12zm11 3a3 3 0 100-6 3 3 0 000 6z" />
                  </svg>
                </div>
                <div>
                  <div className="text-xl font-bold font-mono text-sre-text tracking-tight">
                    Be Observant
                  </div>
                </div>
              </div>
            </div>

            <nav className="hidden md:flex items-center gap-1" aria-label="Main navigation">
              <NavLink
                to="/"
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-2 ${
                    isActive
                      ? 'bg-sre-primary/10 text-sre-primary shadow-glow-sm'
                      : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
                  }`
                }
              >
                <span className="material-icons text-sm leading-none" aria-hidden>dashboard</span>{' '}Dashboard
              </NavLink>
                {hasPermission('read:traces') && (
                <NavLink
                  to="/tempo"
                  className={({ isActive }) =>
                    `px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-2 ${
                      isActive
                        ? 'bg-sre-primary/10 text-sre-primary shadow-glow-sm'
                        : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
                    }`
                  }
                >
                  <span className="material-icons text-sm leading-none" aria-hidden>timeline</span>{' '}Tempo
                </NavLink>
                )}
              {hasPermission('read:logs') && (
              <NavLink
                to="/loki"
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-2 ${
                    isActive
                      ? 'bg-sre-primary/10 text-sre-primary shadow-glow-sm'
                      : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
                  }`
                }
              >
                <span className="material-icons text-sm leading-none" aria-hidden>search</span>{' '}Loki
              </NavLink>
              )}
              {hasPermission('read:alerts') && (
              <NavLink
                to="/alertmanager"
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-2 ${
                    isActive
                      ? 'bg-sre-primary/10 text-sre-primary shadow-glow-sm'
                      : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
                  }`
                }
              >
                <span className="material-icons text-sm leading-none" aria-hidden>notifications</span>{' '}AlertManager
              </NavLink>
              )}
              {hasPermission('read:dashboards') && (
              <NavLink
                to="/grafana"
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-2 ${
                    isActive
                      ? 'bg-sre-primary/10 text-sre-primary shadow-glow-sm'
                      : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
                  }`
                }
              >
                <span className="material-icons text-sm leading-none" aria-hidden>analytics</span>{' '}Grafana
              </NavLink>
              )}
              
            </nav>

              <div className="flex items-center gap-3">
              <ThemeToggle />

              <div className="relative">
                <UserMenu user={user} logout={logout} hasPermission={hasPermission} openChangePassword={() => setShowChangePassword(true)} />
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
          <NavLink
            to="/"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap flex items-center gap-2 transition-all ${
                isActive
                  ? 'bg-sre-primary/10 text-sre-primary'
                  : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
              }`
            }
          >
            <span className="material-icons text-sm leading-none" aria-hidden>dashboard</span>{' '}Dashboard
          </NavLink>
          {hasPermission('read:traces') && (
          <NavLink
            to="/tempo"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap flex items-center gap-2 transition-all ${
                isActive
                  ? 'bg-sre-primary/10 text-sre-primary'
                  : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
              }`
            }
          >
            <span className="material-icons text-sm leading-none" aria-hidden>timeline</span>{' '}Tempo
          </NavLink>
          )}
          {hasPermission('read:logs') && (
          <NavLink
            to="/loki"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap flex items-center gap-2 transition-all ${
                isActive
                  ? 'bg-sre-primary/10 text-sre-primary'
                  : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
              }`
            }
          >
            <span className="material-icons text-sm leading-none" aria-hidden>search</span>{' '}Loki
          </NavLink>
          )}
          {hasPermission('read:alerts') && (
          <NavLink
            to="/alertmanager"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap flex items-center gap-2 transition-all ${
                isActive
                  ? 'bg-sre-primary/10 text-sre-primary'
                  : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
              }`
            }
          >
            <span className="material-icons text-sm leading-none" aria-hidden>notifications</span>{' '}AlertManager
          </NavLink>
          )}
          {hasPermission('read:dashboards') && (
          <NavLink
            to="/grafana"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap flex items-center gap-2 transition-all ${
                isActive
                  ? 'bg-sre-primary/10 text-sre-primary'
                  : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
              }`
            }
          >
            <span className="material-icons text-sm leading-none" aria-hidden>analytics</span>{' '}Grafana
          </NavLink>
          )}
        </div>
      </header>
  )
}

function UserMenu({ user, logout, hasPermission, openChangePassword }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const menuRef = useRef(null)

  useEffect(() => {
    const onClick = (e) => {
      if (!ref.current) return
      if (!ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('click', onClick)
    return () => document.removeEventListener('click', onClick)
  }, [])

  useEffect(() => {
    if (open) {
      // focus the menu container for keyboard support
      setTimeout(() => menuRef.current?.focus(), 0)
    }
  }, [open])

  const navigate = useNavigate()

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
        <span className="hidden sm:block text-sre-text">{user?.username}</span>
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

          <button type="button" role="menuitem" onClick={() => { setOpen(false); openChangePassword?.(); }} className="w-full text-left px-3 py-2 text-sm text-sre-text hover:bg-sre-surface/50">
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

