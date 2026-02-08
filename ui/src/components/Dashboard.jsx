import { useEffect, useState } from 'react'
import { fetchHealth, getAlerts } from '../api'
import { Card, Badge, MetricCard, Spinner } from './ui'
import PropTypes from 'prop-types'

export default function Dashboard({ info }) {
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [alertCount, setAlertCount] = useState(null)
  const [loadingAlerts, setLoadingAlerts] = useState(true)

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
      .finally(() => setLoading(false))

    setLoadingAlerts(true)
    getAlerts()
      .then((data) => {
        setAlertCount(Array.isArray(data) ? data.length : 0)
      })
      .catch(() => setAlertCount(0))
      .finally(() => setLoadingAlerts(false))
  }, [])

  const statusBadge = (status) => {
    if (!status) return <Badge variant="warning">unknown</Badge>
    if (status === 'Healthy') return <Badge variant="success">Healthy</Badge>
    return <Badge variant="error">{status}</Badge>
  }

  const services = [
    {
      name: 'Tempo',
      description: 'Distributed Tracing',
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
      status: 'operational',
    },
    {
      name: 'Loki',
      description: 'Log Aggregation',
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      ),
      status: 'operational',
    },
    {
      name: 'AlertManager',
      description: 'Alert Management',
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
      ),
      status: 'operational',
    },
    {
      name: 'Grafana',
      description: 'Visualization & Dashboards',
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      ),
      status: 'operational',
    },
  ]

  const getStatusValue = () => {
    if (loading) return <Spinner size="sm" />
    return health?.status ? health?.status.charAt(0).toUpperCase() + health?.status.slice(1) : 'Unknown'
  }

  const getAlertValue = () => {
    if (loadingAlerts) return <Spinner size="sm" />
    if (alertCount === null) return '0'
    return String(alertCount)
  }

  return (
    <div className="animate-fade-in">
      {/* Hero Section */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-sre-text mb-2">
          Observability Dashboard
        </h1>
        <p className="text-sre-text-muted">
          Monitor and manage your observability infrastructure in real-time
        </p>
      </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <MetricCard
            label="Service Status"
            value={getStatusValue()}
            trend={health?.status === 'Healthy' ? 'All systems operational' : 'Issues detected'}
            status={health?.status === 'Healthy' ? 'success' : 'warning'}
            icon={
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            }
          />
          <MetricCard
            label="Active Alerts"
            value={getAlertValue()}
            trend={alertCount > 0 ? `${alertCount} active` : 'No active alerts'}
            status={alertCount > 0 ? 'warning' : 'success'}
            icon={
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
              </svg>
            }
          />
          <MetricCard
            label="Active Services"
            value="4"
            trend="All operational"
            status="success"
            icon={
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
            </svg>
            }
          />
        </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Service Info */}
        <Card
          title="Service Information"
          subtitle="Core service details"
          className="lg:col-span-1"
        >
          <div className="space-y-4">
            <div>
              <div className="text-sm text-sre-text-muted mb-1">Service Name</div>
              <div className="text-lg font-mono font-semibold text-sre-text">
                {info?.service || 'beObservant'}
              </div>
            </div>
            <div>
              <div className="text-sm text-sre-text-muted mb-1">Version</div>
              <div className="text-lg font-mono font-semibold text-sre-primary">
                {info?.version || 'v1.0.0'}
              </div>
            </div>
            <div>
              <div className="text-sm text-sre-text-muted mb-1">Health Status</div>
              <div className="flex items-center gap-2 mt-2">
                {statusBadge(health?.status)}
              </div>
            </div>
          </div>
        </Card>
        
        {/* Connected Services */}
        <Card
          title="Connected Services"
          subtitle="Observability stack components"
          className="lg:col-span-2"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {services.map((service) => (
              <div
                key={service.name}
                className="flex items-start gap-3 p-4 bg-sre-bg-alt rounded-lg border border-sre-border hover:border-sre-primary/50 transition-all duration-200"
              >
                <div className="flex-shrink-0 w-10 h-10 bg-sre-primary/10 rounded-lg flex items-center justify-center text-sre-primary">
                  {service.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sre-text">{service.name}</div>
                  <div className="text-sm text-sre-text-muted mt-0.5">
                    {service.description}
                  </div>
                  <div className="mt-2">
                    <Badge variant="success" className="text-xs">
                      {service.status}
                    </Badge>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}

Dashboard.propTypes = {
  info: PropTypes.shape({
    service: PropTypes.string,
    version: PropTypes.string,
  }),
}
