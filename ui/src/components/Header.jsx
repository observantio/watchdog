import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import ThemeToggle from './ThemeToggle'
import { Button } from './ui'

export default function Header() {
  const [apiKey, setApiKey] = useState('')

  useEffect(() => {
    const stored = globalThis.window.localStorage.getItem('beobservantApiKey')
    if (stored) setApiKey(stored)
  }, [])

  const handleSaveApiKey = () => {
    const trimmed = apiKey.trim()
    if (trimmed) {
      globalThis.window.localStorage.setItem('beobservantApiKey', trimmed)
    } else {
      globalThis.window.localStorage.removeItem('beobservantApiKey')
    }
  }

  return (
    <header className="sticky top-0 z-50 bg-sre-surface/80 backdrop-blur-xl border-b border-sre-border shadow-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo & Brand */}
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                  <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12zm11 3a3 3 0 100-6 3 3 0 000 6z" />
                  </svg>
                </div>
                <div>
                  <div className="text-xl font-bold font-mono text-sre-text tracking-tight">
                    BeObservant
                  </div>
                  <div className="text-xs text-sre-text-muted font-medium hidden sm:block">
                   Observing your entire Infrastructure
                  </div>
                </div>
              </div>
            </div>

            {/* Navigation */}
            <nav className="hidden md:flex items-center gap-1" aria-label="Main navigation">
              <NavLink
                to="/"
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? 'bg-sre-primary/10 text-sre-primary shadow-glow-sm'
                      : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
                  }`
                }
              >
                Dashboard
              </NavLink>
              <NavLink
                to="/tempo"
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? 'bg-sre-primary/10 text-sre-primary shadow-glow-sm'
                      : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
                  }`
                }
              >
                Tempo
              </NavLink>
              <NavLink
                to="/loki"
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? 'bg-sre-primary/10 text-sre-primary shadow-glow-sm'
                      : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
                  }`
                }
              >
                Loki
              </NavLink>
              <NavLink
                to="/alertmanager"
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? 'bg-sre-primary/10 text-sre-primary shadow-glow-sm'
                      : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
                  }`
                }
              >
                AlertManager
              </NavLink>
              <NavLink
                to="/grafana"
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? 'bg-sre-primary/10 text-sre-primary shadow-glow-sm'
                      : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
                  }`
                }
              >
                Grafana
              </NavLink>
            </nav>

            {/* API Key + Theme Toggle */}
            <div className="flex items-center gap-2">
              <div className="hidden lg:flex items-center gap-2">
                <label htmlFor="apiKey" className="text-xs text-sre-text-muted">API Key</label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  onBlur={handleSaveApiKey}
                  placeholder="Set API key"
                  className="px-2 py-1 bg-sre-surface border border-sre-border rounded text-xs text-sre-text w-40"
                />
                <Button size="sm" variant="ghost" type="button" onClick={handleSaveApiKey}>Save</Button>
              </div>
              <ThemeToggle />
            </div> 
          </div>
        </div>

        {/* Mobile Navigation */}
        <div className="md:hidden border-t border-sre-border px-4 py-2 flex gap-2 overflow-x-auto">
          <NavLink
            to="/"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${
                isActive
                  ? 'bg-sre-primary/10 text-sre-primary'
                  : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
              }`
            }
          >
            Dashboard
          </NavLink>
          <NavLink
            to="/tempo"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${
                isActive
                  ? 'bg-sre-primary/10 text-sre-primary'
                  : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
              }`
            }
          >
            Tempo
          </NavLink>
          <NavLink
            to="/loki"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${
                isActive
                  ? 'bg-sre-primary/10 text-sre-primary'
                  : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
              }`
            }
          >
            Loki
          </NavLink>
          <NavLink
            to="/alertmanager"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${
                isActive
                  ? 'bg-sre-primary/10 text-sre-primary'
                  : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
              }`
            }
          >
            AlertManager
          </NavLink>
          <NavLink
            to="/grafana"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${
                isActive
                  ? 'bg-sre-primary/10 text-sre-primary'
                  : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light'
              }`
            }
          >
            Grafana
          </NavLink>
        </div>
      </header>
  )
}
