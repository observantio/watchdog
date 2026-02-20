`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

export const SERVICES = [
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

export const getMetricsConfig = (data) => {
  const {
    loadingHealth,
    health,
    loadingAlerts,
    alertCount,
    loadingTraces,
    traceCount,
    traceErrorCount,
    loadingLogs,
    logVolume,
    loadingDashboards,
    dashboardCount,
    loadingSilences,
    silenceCount,
    loadingDatasources,
    datasourceCount,
  } = data

  const getStatusValue = () => {
    if (loadingHealth) return <span className="animate-pulse">Loading...</span>
    return health?.status ? health?.status.charAt(0).toUpperCase() + health?.status.slice(1) : 'Unknown'
  }

  const getAlertValue = () => {
    if (loadingAlerts) return <span className="animate-pulse">Loading...</span>
    if (alertCount === null) return '0'
    return String(alertCount)
  }

  const getTraceValue = () => {
    if (loadingTraces) return <span className="animate-pulse">Loading...</span>
    if (traceCount !== null) {
      if (traceCount >= 1000) return '1000+'
      return String(traceCount)
    }
    return 'N/A'
  }

  const getTraceStatus = () => {
    if (traceErrorCount === null) return traceCount > 0 ? 'success' : 'default'
    if (traceErrorCount > 0) return 'warning'
    if (traceCount > 0) return 'success'
    return 'default'
  }

  const getLogValue = () => {
    if (loadingLogs) return <span className="animate-pulse">Loading...</span>
    if (logVolume !== null) return String(logVolume)
    return 'N/A'
  }

  const getDashboardValue = () => {
    if (loadingDashboards) return <span className="animate-pulse">Loading...</span>
    if (dashboardCount !== null) return String(dashboardCount)
    return 'N/A'
  }

  const getSilenceValue = () => {
    if (loadingSilences) return <span className="animate-pulse">Loading...</span>
    if (silenceCount !== null) return String(silenceCount)
    return 'N/A'
  }

  const getDatasourceValue = () => {
    if (loadingDatasources) return <span className="animate-pulse">Loading...</span>
    if (datasourceCount !== null) return String(datasourceCount)
    return 'N/A'
  }

  const traceTrend = traceErrorCount > 0 ? `${traceErrorCount} with errors` : traceCount > 0 ? 'No errors' : 'No traces'

  return [
    {
      id: 'service-status',
      label: "Service Status",
      value: getStatusValue(),
      trend: health?.status === 'Healthy' ? 'All systems operational' : 'Issues detected',
      status: health?.status === 'Healthy' ? 'success' : 'warning',
      icon: (
        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    {
      id: 'active-alerts',
      label: "Active Alerts",
      value: getAlertValue(),
      trend: alertCount > 0 ? `${alertCount} active` : 'No active alerts',
      status: alertCount > 0 ? 'warning' : 'success',
      icon: (
        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
      ),
    },
    {
      id: 'traces',
      label: "Traces (last 1h)",
      value: getTraceValue(),
      trend: traceTrend,
      status: getTraceStatus(),
      icon: (
        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3v18h18" />
        </svg>
      ),
    },
    {
      id: 'logs',
      label: "Logs (last 1h)",
      value: getLogValue(),
      trend: logVolume > 0 ? 'Log volume detected' : 'No logs',
      status: logVolume > 0 ? 'success' : 'default',
      icon: (
        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12h18M3 6h18M3 18h18" />
        </svg>
      ),
    },
    {
      id: 'active-services',
      label: "Active Services",
      value: String(SERVICES.length),
      trend: SERVICES.length ? `${SERVICES.length} connected` : 'No services connected',
      status: "success",
      icon: (
        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
        </svg>
      ),
    },
    {
      id: 'grafana-dashboards',
      label: "Grafana Dashboards",
      value: getDashboardValue(),
      trend: dashboardCount > 0 ? `${dashboardCount} dashboards available` : 'No dashboards',
      status: dashboardCount > 0 ? 'success' : 'default',
      icon: (
        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      ),
    },
    {
      id: 'alert-silences',
      label: "Alert Silences",
      value: getSilenceValue(),
      trend: silenceCount > 0 ? `${silenceCount} active silences` : 'No active silences',
      status: silenceCount > 0 ? 'warning' : 'success',
      icon: (
        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15zM17 7l-5 5m0 0l5 5m-5-5h7" />
        </svg>
      ),
    },
    {
      id: 'grafana-datasources',
      label: "Grafana Datasources",
      value: getDatasourceValue(),
      trend: datasourceCount > 0 ? `${datasourceCount} datasources configured` : 'No datasources',
      status: datasourceCount > 0 ? 'success' : 'default',
      icon: (
        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
        </svg>
      ),
    },
  ]
}