/**
 * Main App component with routing and error boundaries
 */
import { useEffect, useState, lazy, Suspense } from 'react'
import PropTypes from 'prop-types'
import { HashRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom'
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
const GrafanaPage = lazy(() => import('./pages/GrafanaPage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const UsersPage = lazy(() => import('./pages/UsersPage'))
const GroupsPage = lazy(() => import('./pages/GroupsPage'))
const ApiKeyPage = lazy(() => import('./pages/ApiKeyPage'))

function PageLoader() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <Spinner size="lg" />
    </div>
  )
}

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return <PageLoader />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return children
}

ProtectedRoute.propTypes = {
  children: PropTypes.node
}

function AppContent() {
  const [info, setInfo] = useState(null)
  const { isAuthenticated, user, refreshUser } = useAuth()
  const [showPasswordChange, setShowPasswordChange] = useState(false)
  const location = useLocation()

  useEffect(() => {
    if (isAuthenticated) {
      fetchInfo()
        .then(setInfo)
        .catch(() => setInfo(null))
      
      // Check if user needs to change password
      if (user?.needs_password_change) {
        setShowPasswordChange(true)
      }
    }
  }, [isAuthenticated, user])

  const handlePasswordChangeClose = async () => {
    setShowPasswordChange(false)
    // Refresh user data to get updated needs_password_change flag
    await refreshUser()
  }

  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-b from-sre-bg via-sre-bg-alt to-sre-bg">
      {isAuthenticated && <Header />}
      {user?.needs_password_change && (
        <ChangePasswordModal
          isOpen={showPasswordChange}
          onClose={handlePasswordChangeClose}
          userId={user.id}
          isForced={true}
        />
      )}
      <main className={isAuthenticated ? "container flex-1 mt-4" : "flex-1"}>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={
              <ProtectedRoute>
                <Dashboard info={info} />
              </ProtectedRoute>
            } />
            <Route path="/tempo" element={
              <ProtectedRoute>
                <PermissionGuard any={["read:traces"]} fallback={<div className="p-6 text-center text-sre-text-muted">You don't have access to this page.</div>}>
                  <TempoPage />
                </PermissionGuard>
              </ProtectedRoute>
            } />
            <Route path="/loki" element={
              <ProtectedRoute>
                <PermissionGuard any={["read:logs"]} fallback={<div className="p-6 text-center text-sre-text-muted">You don't have access to this page.</div>}>
                  <LokiPage />
                </PermissionGuard>
              </ProtectedRoute>
            } />
            <Route path="/alertmanager" element={
              <ProtectedRoute>
                <PermissionGuard any={["read:alerts"]} fallback={<div className="p-6 text-center text-sre-text-muted">You don't have access to this page.</div>}>
                  <AlertManagerPage />
                </PermissionGuard>
              </ProtectedRoute>
            } />
            <Route path="/grafana" element={
              <ProtectedRoute>
                <PermissionGuard any={["read:dashboards"]} fallback={<div className="p-6 text-center text-sre-text-muted">You don't have access to this page.</div>}>
                  <GrafanaPage />
                </PermissionGuard>
              </ProtectedRoute>
            } />
            <Route path="/users" element={
              <ProtectedRoute>
                <UsersPage />
              </ProtectedRoute>
            } />
            <Route path="/groups" element={
              <ProtectedRoute>
                <GroupsPage />
              </ProtectedRoute>
            } />
            <Route path="/apikey" element={
              <ProtectedRoute>
                <ApiKeyPage />
              </ProtectedRoute>
            } />
          </Routes>
        </Suspense>
      </main>

      {location.pathname !== '/login' && (
        <footer className="container text-center text-xs text-sre-text-muted mt-8 mb-8">
          © Be Observant — MIT License
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
