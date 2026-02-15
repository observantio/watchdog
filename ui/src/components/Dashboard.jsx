import { useEffect, useState } from 'react'
import { fetchHealth, getAlerts, getLogVolume, getActiveAgents, searchDashboards, getSilences, getDatasources, fetchSystemMetrics, fetchTraceMetrics, getTraceVolume } from '../api'
import { Card, Badge, MetricCard, Spinner } from './ui'
import LogVolume from '../components/loki/LogVolume'
import TraceVolume from '../components/tempo/TraceVolume'
import { getVolumeValues } from '../utils/lokiQueryUtils'
import { useAuth } from '../contexts/AuthContext'
import PropTypes from 'prop-types'

const AgentStatusBadges = ({ agent }) => (
  <div className="flex flex-wrap items-center justify-end gap-2">
    {!agent.is_enabled && <Badge variant="warning">Disabled</Badge>}
    <Badge
      variant={agent.active ? "success" : "default"}
      className={agent.active ? "animate-pulse" : ""}
    >
      {agent.active ? "Active" : "Idle"}
    </Badge>
    <Badge variant={agent.clean ? "success" : "warning"}>
      {agent.clean ? "Clean" : "Check"}
    </Badge>
  </div>
);

AgentStatusBadges.propTypes = {
  agent: PropTypes.shape({
    is_enabled: PropTypes.bool,
    active: PropTypes.bool,
    clean: PropTypes.bool,
  }).isRequired,
};

const formatActivityLabel = (agent) => {
  const parts = [
    agent.metrics_count > 0 && `Metrics: ${agent.metrics_count}`
  ].filter(Boolean);
  
  return parts.length > 0 ? parts.join(' · ') : 'No activity';
};

const AgentCard = ({ agent }) => {
  const hostLabel = agent.host_names?.length > 0
    ? agent.host_names.join(', ')
    : null;
  const activityLabel = formatActivityLabel(agent);

  return (
    <div className="rounded-lg border border-sre-border bg-sre-bg-alt px-4 py-3">
      <div className="flex items-center gap-4">
        <div className="flex-1">
          <div className="font-semibold text-sre-text text-left">{agent?.name}</div>
          <div className="text-xs text-sre-text-muted text-left">{activityLabel}</div>
          {hostLabel && (
            <div className="text-xs text-sre-text-muted text-left">Host: {hostLabel}</div>
          )}
        </div>
        <AgentStatusBadges agent={agent} />
      </div>
    </div>
  );
};

AgentCard.propTypes = {
  agent: PropTypes.shape({
    name: PropTypes.string.isRequired,
    host_names: PropTypes.arrayOf(PropTypes.string),
    metrics_count: PropTypes.number,
    is_enabled: PropTypes.bool,
    active: PropTypes.bool,
    clean: PropTypes.bool,
  }).isRequired,
};

const AgentActivityContent = ({ loading, agents }) => {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sre-text-muted text-left">
        <Spinner size="sm" /> Loading activity
      </div>
    );
  }

  if (agents.length === 0) {
    return (
      <div className="text-sm text-sre-text-muted text-left">
        No agent activity detected.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {agents.map((agent) => (
        <AgentCard key={agent.name} agent={agent} />
      ))}
    </div>
  );
};

AgentActivityContent.propTypes = {
  loading: PropTypes.bool.isRequired,
  agents: PropTypes.array.isRequired,
};

export default function Dashboard({ info }) {
  const { hasPermission } = useAuth()
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [alertCount, setAlertCount] = useState(null)
  const [loadingAlerts, setLoadingAlerts] = useState(true)
  const [traceCount, setTraceCount] = useState(null)
  const [traceErrorCount, setTraceErrorCount] = useState(null)
  const [loadingTraces, setLoadingTraces] = useState(true)
  const [logVolume, setLogVolume] = useState(null)
  const [logVolumeSeries, setLogVolumeSeries] = useState([])
  const [loadingLogs, setLoadingLogs] = useState(true)
  const [tempoVolumeSeries, setTempoVolumeSeries] = useState([])
  const [loadingTempoVolume, setLoadingTempoVolume] = useState(true)
  const [agentActivity, setAgentActivity] = useState([])
  const [loadingAgents, setLoadingAgents] = useState(true)
  const [dashboardCount, setDashboardCount] = useState(null)
  const [loadingDashboards, setLoadingDashboards] = useState(true)
  const [silenceCount, setSilenceCount] = useState(null)
  const [loadingSilences, setLoadingSilences] = useState(true)
  const [datasourceCount, setDatasourceCount] = useState(null)
  const [loadingDatasources, setLoadingDatasources] = useState(true)
  const [systemMetrics, setSystemMetrics] = useState(null)
  const [loadingSystemMetrics, setLoadingSystemMetrics] = useState(true)
  const [draggedIndex, setDraggedIndex] = useState(null)
  const [metricOrder, setMetricOrder] = useState(() => {
    const saved = localStorage.getItem('dashboard-metric-order')
    if (saved) {
      const parsed = JSON.parse(saved)
      if (parsed.length < 8) {
        const missingIndices = []
        for (let i = 0; i < 8; i++) {
          if (!parsed.includes(i)) {
            missingIndices.push(i)
          }
        }
        const updated = [...parsed, ...missingIndices]
        localStorage.setItem('dashboard-metric-order', JSON.stringify(updated))
        return updated
      }
      return parsed
    }
    return [0, 1, 2, 3, 4, 5, 6, 7]
  })
  const [layoutOrder, setLayoutOrder] = useState(() => {
    const saved = localStorage.getItem('dashboard-layout-order')
    return saved ? JSON.parse(saved) : [0, 1, 2, 3]
  })

  const computeLogTotal = (vol) => {
    if (!vol?.data?.result || !Array.isArray(vol.data.result)) return 0
    let total = 0
    for (const series of vol.data.result) {
      if (!Array.isArray(series.values)) continue
      for (const v of series.values) {
        const val = Number(v[1])
        if (!Number.isNaN(val)) total += val
      }
    }
    return total
  }

  useEffect(() => {
    ;(async () => {
      try {
        const res = await fetchHealth()
        setHealth(res)
      } catch {
        setHealth(null)
      } finally {
        setLoading(false)
      }
    })()

    ;(async () => {
      try {
        setLoadingAlerts(true)
        const data = await getAlerts()
        setAlertCount(Array.isArray(data) ? data.length : 0)
      } catch {
        setAlertCount(0)
      } finally {
        setLoadingAlerts(false)
      }
    })()

    ;(async () => {
      try {
        const endUs = Date.now() * 1000 // ms -> µs
        const startUs = endUs - (60 * 60 * 1000000) // last 1 hour in µs
        const metrics = await fetchTraceMetrics({ start: Math.floor(startUs), end: Math.floor(endUs) })
        setTraceCount(typeof metrics?.total_traces === 'number' ? metrics.total_traces : 0)
        setTraceErrorCount(typeof metrics?.error_count === 'number' ? metrics.error_count : null)
      } catch {
        setTraceCount(0)
        setTraceErrorCount(null)
      } finally {
        setLoadingTraces(false)
      }
    })()

    ;(async () => {
      try {
        const endNs = Date.now() * 1000000 // ms -> ns
        const startNs = endNs - (60 * 60 * 1000000000) // last 1 hour in ns
        const vol = await getLogVolume('{service_name=~".+"}', { start: Math.floor(startNs), end: Math.floor(endNs), step: 60 })
        let total = 0
        try {
          total = computeLogTotal(vol)
        } catch {
          // If computing the total fails, default to 0 so the metric displays "0"
          total = 0
        }
        setLogVolume(total)
        // store series for LogVolume sparkline
        try {
          const series = getVolumeValues(vol)
          setLogVolumeSeries(series)
        } catch (e) {
          setLogVolumeSeries([])
        }
      } catch {
        // On error fetching logs, show 0 instead of leaving the metric as N/A
        setLogVolume(0)
        setLogVolumeSeries([])
      } finally {
        setLoadingLogs(false)
      }
    })()

    ;(async () => {
      try {
        setLoadingTempoVolume(true)
        const endUs = Date.now() * 1000 // ms -> µs
        const startUs = endUs - (60 * 60 * 1000000) // last 1 hour in µs
        const res = await getTraceVolume({ start: Math.floor(startUs), end: Math.floor(endUs), step: 60 })
        try {
          const series = getVolumeValues(res)
          setTempoVolumeSeries(series)
        } catch (e) {
          setTempoVolumeSeries([])
        }
      } catch (e) {
        setTempoVolumeSeries([])
      } finally {
        setLoadingTempoVolume(false)
      }
    })()

    ;(async () => {
      try {
        setLoadingAgents(true)
        const res = await getActiveAgents()
        setAgentActivity(Array.isArray(res) ? res : [])
      } catch {
        setAgentActivity([])
      } finally {
        setLoadingAgents(false)
      }
    })()

    ;(async () => {
      if (!hasPermission('read:dashboards')) {
        setLoadingDashboards(false)
        return
      }
      try {
        setLoadingDashboards(true)
        const data = await searchDashboards()
        setDashboardCount(Array.isArray(data) ? data.length : 0)
      } catch {
        setDashboardCount(0)
      } finally {
        setLoadingDashboards(false)
      }
    })()

    ;(async () => {
      if (!hasPermission('read:alerts')) {
        setLoadingSilences(false)
        return
      }
      try {
        setLoadingSilences(true)
        const data = await getSilences()
        setSilenceCount(Array.isArray(data) ? data.length : 0)
      } catch {
        setSilenceCount(0)
      } finally {
        setLoadingSilences(false)
      }
    })()

    ;(async () => {
      if (!hasPermission('read:dashboards')) {
        setLoadingDatasources(false)
        return
      }
      try {
        setLoadingDatasources(true)
        const data = await getDatasources()
        setDatasourceCount(Array.isArray(data) ? data.length : 0)
      } catch {
        setDatasourceCount(0)
      } finally {
        setLoadingDatasources(false)
      }
    })()

    ;(async () => {
      try {
        setLoadingSystemMetrics(true)
        const data = await fetchSystemMetrics()
        setSystemMetrics(data)
      } catch {
        setSystemMetrics(null)
      } finally {
        setLoadingSystemMetrics(false)
      }
    })()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  const getTraceValue = () => {
    if (loadingTraces) return <Spinner size="sm" />
    if (traceCount !== null) return String(traceCount)
    return 'N/A'
  }

  const getTraceStatus = () => {
    if (traceErrorCount === null) return traceCount > 0 ? 'success' : 'default'
    if (traceErrorCount > 0) return 'warning'
    if (traceCount > 0) return 'success'
    return 'default'
  }

  const getLogValue = () => {
    if (loadingLogs) return <Spinner size="sm" />
    if (logVolume !== null) return String(logVolume)
    return 'N/A'
  }

  const getDashboardValue = () => {
    if (loadingDashboards) return <Spinner size="sm" />
    if (dashboardCount !== null) return String(dashboardCount)
    return 'N/A'
  }

  const getSilenceValue = () => {
    if (loadingSilences) return <Spinner size="sm" />
    if (silenceCount !== null) return String(silenceCount)
    return 'N/A'
  }

  const getDatasourceValue = () => {
    if (loadingDatasources) return <Spinner size="sm" />
    if (datasourceCount !== null) return String(datasourceCount)
    return 'N/A'
  }

  const traceTrend = traceErrorCount > 0 ? `${traceErrorCount} with errors` : traceCount > 0 ? 'No errors' : 'No traces'

  const metrics = [
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
      value: String(services.length),
      trend: services.length ? `${services.length} connected` : 'No services connected',
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

  const handleDragStart = (e, index) => {
    setDraggedIndex(index)
    e.dataTransfer.effectAllowed = 'move'
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  const handleDrop = (e, dropIndex) => {
    e.preventDefault()
    if (draggedIndex === null || draggedIndex === dropIndex) return

    const newOrder = [...metricOrder]
    const draggedItem = newOrder[draggedIndex]
    newOrder.splice(draggedIndex, 1)
    newOrder.splice(dropIndex, 0, draggedItem)

    setMetricOrder(newOrder)
    localStorage.setItem('dashboard-metric-order', JSON.stringify(newOrder))
    setDraggedIndex(null)
  }

  const handleDragEnd = () => {
    setDraggedIndex(null)
  }

const layoutComponents = [
    {
      id: 'connected-services',
      title: "Connected Services",
      subtitle: "Observability stack components",
      className: "lg:col-span-2",
      content: (
        <div className="grid grid-cols-1 gap-6">
          {services.map((service) => (
            <div
              key={service.name}
              className="flex items-center gap-4 p-6 bg-sre-bg-alt rounded-lg border border-sre-border hover:border-sre-primary/50 transition-all duration-200"
            >
              <div className="flex-shrink-0 w-12 h-12 bg-sre-primary/10 rounded-lg flex items-center justify-center text-sre-primary">
                {service.icon}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-sre-text text-left text-lg">{service.name}</div>
                <div className="text-sm text-sre-text-muted mt-1 text-left">
                  {service.description}
                </div>
              </div>
            </div>
          ))}
        </div>
      )
    },

    {
      id: 'active-otel-agents',
      title: "Active OTEL Agents",
      subtitle: "Agents Activity",
      className: "lg:col-span-2",
      content: (
        <AgentActivityContent loading={loadingAgents} agents={agentActivity} />
      )
    },

    {
      id: 'data-volume',
      className: "",
      content: (
        <div className="space-y-4">
          {loadingLogs ? (
            <div className="flex items-center gap-2 text-sre-text-muted"><Spinner size="sm" /> Loading logs...</div>
          ) : (
            <LogVolume volume={logVolumeSeries} />
          )}

          {loadingTempoVolume ? (
            <div className="flex items-center gap-2 text-sre-text-muted"><Spinner size="sm" /> Loading traces...</div>
          ) : (
            <TraceVolume volume={tempoVolumeSeries} />
          )}
        </div>
      )
    },

    {
      id: 'server-metrics',
      title: "Observant Process",
      subtitle: systemMetrics?.stress?.message || "Process resource utilization",
      className: "",
      content: loadingSystemMetrics ? (
        <div className="flex items-center gap-2 text-sre-text-muted text-left">
          <Spinner size="sm" /> Loading metrics...
        </div>
      ) : !systemMetrics ? (
        <div className="text-sm text-sre-text-muted text-left">
          Unable to fetch system metrics
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-3 p-4 rounded-lg border border-sre-border bg-sre-bg-alt">
            <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${
              systemMetrics.stress?.status === 'stressed' ? 'bg-red-500/20 text-red-500' :
              systemMetrics.stress?.status === 'moderate' ? 'bg-yellow-500/20 text-yellow-500' :
              'bg-green-500/20 text-green-500'
            }`}>
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {systemMetrics.stress?.status === 'stressed' ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                )}
              </svg>
            </div>
            <div className="flex-1">
              <div className="font-semibold text-sre-text text-left">
                {systemMetrics.stress?.status === 'stressed' ? 'Server Under Stress' :
                 systemMetrics.stress?.status === 'moderate' ? 'Moderate Load' :
                 'Server Healthy'}
              </div>
              <div className="text-xs text-sre-text-muted text-left mt-1">
                {systemMetrics.stress?.message}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-lg bg-sre-bg-alt border border-sre-border">
              <div className="flex items-center gap-2 mb-2">
                <svg className="w-4 h-4 text-sre-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
                </svg>
                <span className="text-xs font-medium text-sre-text-muted">CPU</span>
              </div>
              <div className="text-lg font-bold text-sre-text">{systemMetrics.cpu?.utilization?.toFixed(1)}%</div>
              <div className="text-xs text-sre-text-muted mt-1">{systemMetrics.cpu?.threads} threads</div>
            </div>

            <div className="p-3 rounded-lg bg-sre-bg-alt border border-sre-border">
              <div className="flex items-center gap-2 mb-2">
                <svg className="w-4 h-4 text-sre-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                </svg>
                <span className="text-xs font-medium text-sre-text-muted">Memory</span>
              </div>
              <div className="text-lg font-bold text-sre-text">{systemMetrics.memory?.utilization?.toFixed(1)}%</div>
              <div className="text-xs text-sre-text-muted mt-1">RSS: {systemMetrics.memory?.rss_mb} MB</div>
            </div>

            <div className="p-3 rounded-lg bg-sre-bg-alt border border-sre-border">
              <div className="flex items-center gap-2 mb-2">
                <svg className="w-4 h-4 text-sre-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                </svg>
                <span className="text-xs font-medium text-sre-text-muted">I/O</span>
              </div>
              <div className="text-lg font-bold text-sre-text">{(systemMetrics.io?.read_mb + systemMetrics.io?.write_mb)?.toFixed(1)} MB</div>
              <div className="text-xs text-sre-text-muted mt-1">↑{systemMetrics.io?.write_mb} ↓{systemMetrics.io?.read_mb}</div>
            </div>

            <div className="p-3 rounded-lg bg-sre-bg-alt border border-sre-border">
              <div className="flex items-center gap-2 mb-2">
                <svg className="w-4 h-4 text-sre-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
                </svg>
                <span className="text-xs font-medium text-sre-text-muted">Connections</span>
              </div>
              <div className="text-lg font-bold text-sre-text">{systemMetrics.network?.total_connections || 0}</div>
              <div className="text-xs text-sre-text-muted mt-1">{systemMetrics.network?.established || 0} active</div>
            </div>
          </div>

          {systemMetrics.stress?.issues?.length > 0 && (
            <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30">
              <div className="text-xs font-medium text-yellow-600 mb-1">Active Issues</div>
              <ul className="space-y-1">
                {systemMetrics.stress.issues.map((issue, idx) => (
                  <li key={idx} className="text-xs text-sre-text-muted">• {issue}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )
    }
  ]

  const sanitizedLayoutOrder = (() => {
    const max = layoutComponents.length
    const seen = new Set()
    const parsed = Array.isArray(layoutOrder) ? layoutOrder : []
    const result = []
    for (const idx of parsed) {
      if (typeof idx === 'number' && idx >= 0 && idx < max && !seen.has(idx)) {
        result.push(idx)
        seen.add(idx)
      }
    }
    // Append any missing indices so we always render all sections
    for (let i = 0; i < max; i++) {
      if (!seen.has(i)) result.push(i)
    }
    return result
  })()

  // Persist cleaned order if it differs from current state (run after first render)
  useEffect(() => {
    try {
      const curr = Array.isArray(layoutOrder) ? layoutOrder : []
      if (JSON.stringify(curr) !== JSON.stringify(sanitizedLayoutOrder)) {
        setLayoutOrder(sanitizedLayoutOrder)
        localStorage.setItem('dashboard-layout-order', JSON.stringify(sanitizedLayoutOrder))
      }
    } catch (e) {
      // Silently handle localStorage failure
    }
  }, [layoutComponents.length])

  const handleLayoutDragStart = (e, index) => {
    setDraggedIndex(index)
    e.dataTransfer.effectAllowed = 'move'
  }

  const handleLayoutDrop = (e, dropIndex) => {
    e.preventDefault()
    if (draggedIndex === null || draggedIndex === dropIndex) return

    const newOrder = [...layoutOrder]
    const draggedItem = newOrder[draggedIndex]
    newOrder.splice(draggedIndex, 1)
    newOrder.splice(dropIndex, 0, draggedItem)

    setLayoutOrder(newOrder)
    localStorage.setItem('dashboard-layout-order', JSON.stringify(newOrder))
    setDraggedIndex(null)
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-sre-text mb-2 text-left flex items-center gap-3">
          <span className="material-icons text-3xl text-sre-primary" aria-hidden>dashboard</span>
          Observability
        </h1>
        <p className="text-sre-text-muted text-left">
          Monitor and manage your observability infrastructure in real-time
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {metricOrder.map((metricIndex, displayIndex) => {
          const metric = metrics[metricIndex]
          return (
            <button
              key={metric.id}
              draggable
              onDragStart={(e) => handleDragStart(e, displayIndex)}
              onDragOver={handleDragOver}
              onDrop={(e) => handleDrop(e, displayIndex)}
              onDragEnd={handleDragEnd}
              className={`cursor-move transition-transform duration-200 ease-out will-change-transform hover:shadow-lg relative ${
                draggedIndex === displayIndex ? 'opacity-50 scale-95 shadow-xl' : ''
              }`}
              title="Drag to rearrange"
              type="button"
            >
              <div className="absolute top-2 right-2 text-sre-text-muted hover:text-sre-text transition-colors z-10">
                <span className="material-icons text-sm drag-handle" aria-hidden>drag_indicator</span>
              </div>
              <MetricCard
                label={metric.label}
                value={metric.value}
                trend={metric.trend}
                status={metric.status}
                icon={metric.icon}
              />
            </button>
          )
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {sanitizedLayoutOrder.map((layoutIndex, displayIndex) => {
          const component = layoutComponents[layoutIndex]
          if (!component) return null
          return (
            <div
              key={component.id}
              className={`transition-transform duration-200 ease-out will-change-transform ${
                draggedIndex === displayIndex ? 'opacity-50 scale-95 shadow-xl' : ''
              }`}
            >
              <Card
                title={component.title}
                subtitle={component.subtitle}
                className={`${component.className} cursor-move relative`}
                draggable
                onDragStart={(e) => handleLayoutDragStart(e, displayIndex)}
                onDragOver={handleDragOver}
                onDrop={(e) => handleLayoutDrop(e, displayIndex)}
                onDragEnd={handleDragEnd}
              >
                <div className="absolute top-4 right-4 text-sre-text-muted hover:text-sre-text transition-colors z-10">
                  <span className="material-icons text-sm drag-handle" aria-hidden>drag_indicator</span>
                </div>
                {component.content}
              </Card>
            </div>
          )
        })}
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
