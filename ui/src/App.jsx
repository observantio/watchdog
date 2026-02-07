/**
 * Main App component with routing and error boundaries
 */
import React, { useEffect, useState, lazy, Suspense } from 'react'
import { HashRouter as Router, Routes, Route } from 'react-router-dom'
import { ThemeProvider } from './contexts/ThemeContext'
import Header from './components/Header'
import Dashboard from './components/Dashboard'
import ErrorBoundary from './components/ErrorBoundary'
import { Spinner } from './components/ui'
import { fetchInfo } from './api'

// Lazy load pages for code splitting
const TempoPage = lazy(() => import('./pages/TempoPage'))
const LokiPage = lazy(() => import('./pages/LokiPage'))
const AlertManagerPage = lazy(() => import('./pages/AlertManagerPage'))
const GrafanaPage = lazy(() => import('./pages/GrafanaPage'))

// Loading fallback component
function PageLoader() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <Spinner size="lg" />
    </div>
  )
}

export default function App() {
  const [info, setInfo] = useState(null)

  useEffect(() => {
    fetchInfo()
      .then(setInfo)
      .catch(() => setInfo(null))
  }, [])

  return (
    <ThemeProvider>
      <ErrorBoundary>
        <Router>
          <div className="min-h-screen bg-gradient-to-b from-sre-bg via-sre-bg-alt to-sre-bg">
            <Header />
            <main className="container">
              <Suspense fallback={<PageLoader />}>
                <Routes>
                  <Route path="/" element={<Dashboard info={info} />} />
                  <Route path="/tempo" element={<TempoPage />} />
                  <Route path="/loki" element={<LokiPage />} />
                  <Route path="/alertmanager" element={<AlertManagerPage />} />
                  <Route path="/grafana" element={<GrafanaPage />} />
                </Routes>
              </Suspense>
            </main>
          </div>
        </Router>
      </ErrorBoundary>
    </ThemeProvider>
  )
}
