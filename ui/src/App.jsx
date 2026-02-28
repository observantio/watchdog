import { useEffect, useState, lazy, Suspense } from 'react'
import PropTypes from 'prop-types'
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { ThemeProvider } from './contexts/ThemeContext'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { ToastProvider } from './contexts/ToastContext'
import Header from './components/Header'
import Dashboard from './components/Dashboard'
import ErrorBoundary from './components/ErrorBoundary'
import ChangePasswordModal from './components/ChangePasswordModal'
import PermissionGuard from './components/PermissionGuard'
import { Spinner } from './components/ui'
import { fetchInfo } from './api'

const TempoPage = lazy(() => import('./pages/TempoPage'))
const LokiPage = lazy(() => import('./pages/LokiPage'))
const AlertManagerPage = lazy(() => import('./pages/AlertManagerPage'))
const IncidentBoardPage = lazy(() => import('./pages/IncidentBoardPage'))
const GrafanaPage = lazy(() => import('./pages/GrafanaPage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const OIDCCallbackPage = lazy(() => import('./pages/OIDCCallbackPage'))
const UsersPage = lazy(() => import('./pages/UsersPage'))
const GroupsPage = lazy(() => import('./pages/GroupsPage'))
const ApiKeyPage = lazy(() => import('./pages/ApiKeyPage'))
const IntegrationsPage = lazy(() => import('./pages/IntegrationsPage'))
const AuditCompliancePage = lazy(() => import('./pages/AuditCompliancePage'))
const RCAPage = lazy(() => import('./pages/RCAPage'))

function PageLoader() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <Spinner size="lg" />
    </div>
  )
}

function AccessDenied() {
  return <div className="p-6 text-center text-sre-text-muted">You don&apos;t have access to this page.</div>
}

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()

  if (loading) return <PageLoader />
  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location }} replace />
  return children
}

ProtectedRoute.propTypes = { children: PropTypes.node }

function ProtectedPermissionRoute({ children, permissions }) {
  return (
    <ProtectedRoute>
      {permissions?.length ? (
        <PermissionGuard any={permissions} fallback={<AccessDenied />}>
          {children}
        </PermissionGuard>
      ) : (
        children
      )}
    </ProtectedRoute>
  )
}

ProtectedPermissionRoute.propTypes = {
  children: PropTypes.node,
  permissions: PropTypes.arrayOf(PropTypes.string),
}

function AppContent() {
  const [info, setInfo] = useState(null)
  const { isAuthenticated, user, refreshUser } = useAuth()
  const [showPasswordChange, setShowPasswordChange] = useState(false)
  const location = useLocation()

  useEffect(() => {
    let cancelled = false

    if (!isAuthenticated) {
      setInfo(null)
      setShowPasswordChange(false)
      return () => {
        cancelled = true
      }
    }

    fetchInfo()
      .then((resp) => {
        if (!cancelled) setInfo(resp)
      })
      .catch(() => {
        if (!cancelled) setInfo(null)
      })

    setShowPasswordChange(Boolean(user?.needs_password_change))

    return () => {
      cancelled = true
    }
  }, [isAuthenticated, user?.needs_password_change])

  const handlePasswordChangeClose = async () => {
    setShowPasswordChange(false)
    await refreshUser()
  }

  const protectedRoutes = [
    { path: '/', element: <Dashboard info={info} /> },
    { path: '/tempo', element: <TempoPage />, permissions: ['read:traces'] },
    { path: '/loki', element: <LokiPage />, permissions: ['read:logs'] },
    { path: '/rca', element: <RCAPage />, permissions: ['read:rca'] },
    { path: '/alertmanager', element: <AlertManagerPage />, permissions: ['read:alerts'] },
    { path: '/incidents', element: <IncidentBoardPage />, permissions: ['read:alerts'] },
    { path: '/grafana', element: <GrafanaPage />, permissions: ['read:dashboards'] },
    { path: '/users', element: <UsersPage /> },
    { path: '/groups', element: <GroupsPage /> },
    { path: '/apikey', element: <ApiKeyPage /> },
    { path: '/integrations', element: <IntegrationsPage />, permissions: ['read:channels'] },
    { path: '/audit-compliance', element: <AuditCompliancePage />, permissions: ['read:audit_logs'] },
  ]

  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-b from-sre-bg via-sre-bg-alt to-sre-bg">
      {isAuthenticated && <Header />}

      {user?.needs_password_change && (
        <ChangePasswordModal
          isOpen={showPasswordChange}
          onClose={handlePasswordChangeClose}
          userId={user.id}
          isForced
        />
      )}

      <main className={isAuthenticated ? 'container flex-1 mt-4' : 'flex-1'}>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/auth/callback" element={<OIDCCallbackPage />} />

            {protectedRoutes.map((route) => (
              <Route
                key={route.path}
                path={route.path}
                element={
                  <ProtectedPermissionRoute permissions={route.permissions}>
                    {route.element}
                  </ProtectedPermissionRoute>
                }
              />
            ))}

            <Route path="*" element={<Navigate to={isAuthenticated ? '/' : '/login'} replace />} />
          </Routes>
        </Suspense>
      </main>

      {location.pathname !== '/login' && (
        <footer className="container text-center text-xs text-sre-text-muted mt-8 mb-8">
          © Be Observant — Apache 2.0 License —{' '}
          <a
            href="https://github.com/StefanKumarasinghe/BeObservant"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sre-primary hover:underline"
          >
            GitHub
          </a>
        </footer>
      )}
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <ErrorBoundary>
        <Router>
          <AuthProvider>
            <ToastProvider>
              <AppContent />
            </ToastProvider>
          </AuthProvider>
        </Router>
      </ErrorBoundary>
    </ThemeProvider>
  )
}