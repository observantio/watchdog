import { useEffect, useState, useMemo } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { fetchTempoServices, searchTraces, getTrace } from '../api'
import { Card, Button, Select, Input, Alert, Badge, Spinner } from '../components/ui'
import ServiceGraph from '../components/tempo/ServiceGraph'
import TraceTimeline from '../components/tempo/TraceTimeline'
import { formatDuration } from '../utils/formatters'
import { getServiceName } from '../utils/helpers'
import { TIME_RANGES, DEFAULT_DURATION_RANGE } from '../utils/constants'

export default function TempoPage() {
  const [services, setServices] = useState([])
  const [service, setService] = useState('')
  const [operation, setOperation] = useState('')
  const [durationRange, setDurationRange] = useState([DEFAULT_DURATION_RANGE.min, DEFAULT_DURATION_RANGE.max])
  const [statusFilter, setStatusFilter] = useState('all')
  const [timeRange, setTimeRange] = useState(60)
  const [traces, setTraces] = useState(null)
  const [selectedTrace, setSelectedTrace] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [viewMode, setViewMode] = useState('list')

  const hasSpanError = (span) => {
    return span.status?.code === 'ERROR' || span.tags?.some(tag => tag.key === 'error' && tag.value === true)
  }

  const { isAuthenticated, loading: authLoading } = useAuth()

  // Load services only after authentication is ready to ensure auth token is set
  useEffect(() => {
    if (isAuthenticated && !authLoading) {
      loadServices()
    }
  }, [isAuthenticated, authLoading])

  // If backend doesn't return services, derive them from loaded traces
  useEffect(() => {
    if (!services?.length && traces?.data?.length) {
      const discovered = new Set()
      traces.data.forEach(t => {
        (t.spans || []).forEach(s => {
          const name = getServiceName(s)
          if (name) discovered.add(name)
        })
      })
      if (discovered.size) setServices(Array.from(discovered).sort((a, b) => a.localeCompare(b)))
    }
  }, [traces])

  async function loadServices() {
    try {
      const data = await fetchTempoServices()
      setServices(data || [])
    } catch (e) {
      setServices([])
      console.error('Failed to load services:', e)
    }
  }

  async function onSearch(e) {
    if (e) e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      const end = Date.now() * 1000
      const start = end - (timeRange * 60 * 1000000)

      const res = await searchTraces({
        service,
        operation,
        minDuration: `${Math.floor(Math.max(0, durationRange[0]) / 1000000)}ms`,
        maxDuration: `${Math.floor(durationRange[1] / 1000000)}ms`,
        start: Math.floor(start),
        end: Math.floor(end),
        limit: 100
      })

      setTraces(res)
      if (!services?.length && res?.data?.length) {
        const discovered = new Set()
        res.data.forEach(t => {
          (t.spans || []).forEach(s => {
            const name = getServiceName(s)
            if (name) discovered.add(name)
          })
        })
        if (discovered.size) setServices(Array.from(discovered).sort((a, b) => a.localeCompare(b)))
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleTraceClick(traceId) {
    try {
      const trace = await getTrace(traceId)
      if (trace?.spans) {
        const enrichedTrace = {
          ...trace,
          spans: trace.spans.map(s => ({
            ...s,
            endTime: s.startTime + (s.duration || 0)
          }))
        }
        setSelectedTrace(enrichedTrace)
      } else {
        setError('Trace data is incomplete')
      }
    } catch (e) {
      setError(`Failed to load trace: ${e.message}`)
    }
  }

  const filteredTraces = useMemo(() => {
    if (!traces?.data) return []

    return traces.data.filter(trace => {
      if (statusFilter === 'error') {
        return trace.spans?.some(hasSpanError)
      }
      if (statusFilter === 'ok') {
        return !trace.spans?.some(hasSpanError)
      }
      return true
    })
  }, [traces, statusFilter])

  const traceStats = useMemo(() => {
    if (!filteredTraces.length) return null

    const durations = filteredTraces.map(t => {
      if (!t.spans || t.spans.length === 0) return 0
      const rootSpan = t.spans.find(s => !s.parentSpanId) || t.spans[0]
      return rootSpan?.duration || 0
    })

    const errorCount = filteredTraces.filter(t =>
      t.spans?.some(hasSpanError)
    ).length

    const validDurations = durations.filter(d => d > 0)
    const avgDuration = validDurations.length > 0 ? validDurations.reduce((a, b) => a + b, 0) / validDurations.length : 0
    const maxDuration = validDurations.length > 0 ? Math.max(...validDurations) : 0
    const minDuration = validDurations.length > 0 ? Math.min(...validDurations) : 0

    return {
      total: filteredTraces.length,
      avgDuration,
      maxDuration,
      minDuration,
      errorRate: (errorCount / filteredTraces.length * 100).toFixed(1),
      errorCount
    }
  }, [filteredTraces])

  return (
    <div className="animate-fade-in">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-sre-text mb-2 flex items-center gap-2">
            <span className="material-icons text-sre-primary text-3xl">timeline</span>
            <span>Distributed Tracing</span>
          </h1>
          <p className="text-sre-text-muted">Search and analyze distributed traces across your services</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setViewMode('list')}
            className={`px-3 py-2 rounded-lg transition-colors ${viewMode === 'list' ? 'bg-sre-primary text-white' : 'bg-sre-surface text-sre-text hover:bg-sre-surface-light'}`}
          >
            <span className="material-icons text-sm">list</span>
          </button>
          <button
            onClick={() => setViewMode('graph')}
            className={`px-3 py-2 rounded-lg transition-colors ${viewMode === 'graph' ? 'bg-sre-primary text-white' : 'bg-sre-surface text-sre-text hover:bg-sre-surface-light'}`}
          >
            <span className="material-icons text-sm">hub</span>
          </button>
        </div>
      </div>

      {error && (
        <Alert variant="error" className="mb-6">
          <strong>Error:</strong> {error}
        </Alert>
      )}

      {traceStats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          <Card className="p-4">
            <div className="text-sre-text-muted text-xs mb-1">Total Traces</div>
            <div className="text-2xl font-bold text-sre-text">{traceStats.total}</div>
          </Card>
          <Card className="p-4">
            <div className="text-sre-text-muted text-xs mb-1">Avg Duration</div>
            <div className="text-2xl font-bold text-sre-text">{formatDuration(traceStats.avgDuration)}</div>
          </Card>
          <Card className="p-4">
            <div className="text-sre-text-muted text-xs mb-1">Max Duration</div>
            <div className="text-2xl font-bold text-sre-text">{formatDuration(traceStats.maxDuration)}</div>
          </Card>
          <Card className="p-4">
            <div className="text-sre-text-muted text-xs mb-1">Error Rate</div>
            <div className={`text-2xl font-bold ${traceStats.errorRate > 5 ? 'text-red-500' : 'text-green-500'}`}>
              {traceStats.errorRate}%
            </div>
          </Card>
          <Card className="p-4">
            <div className="text-sre-text-muted text-xs mb-1">Errors</div>
            <div className="text-2xl font-bold text-red-500">{traceStats.errorCount}</div>
          </Card>
        </div>
      )}

      <Card title="Search Traces" subtitle="Query traces by service, operation, and duration" className="mb-6">
        <form onSubmit={onSearch} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Select
              label="Service"
              value={service}
              onChange={(e) => setService(e.target.value)}
            >
              <option value="">-- All Services --</option>
              {services?.length > 0 ? (
                services.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))
              ) : (
                <option disabled>No services available</option>
              )}
            </Select>

            <Input
              label="Operation"
              value={operation}
              onChange={(e) => setOperation(e.target.value)}
              placeholder="e.g., HTTP GET /api"
            />

            <Select
              label="Time Range"
              value={timeRange}
              onChange={(e) => setTimeRange(Number(e.target.value))}
            >
              {TIME_RANGES.map(tr => (
                <option key={tr.value} value={tr.value}>{tr.label}</option>
              ))}
            </Select>

            <Select
              label="Status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="all">All</option>
              <option value="ok">Success Only</option>
              <option value="error">Errors Only</option>
            </Select>
          </div>

          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              <span className="material-icons text-sm mr-1 align-middle">schedule</span>
              Duration Range: {formatDuration(durationRange[0])} - {formatDuration(durationRange[1])}
            </label>
            <div className="space-y-2">
              <div>
                <label htmlFor="min-duration" className="text-xs text-sre-text-muted">Minimum Duration</label>
                <input
                  type="range"
                  min="0"
                  max="10000000000"
                  step="50000000"
                  value={durationRange[0]}
                  onChange={(e) => {
                    const newMin = Math.max(0, Number(e.target.value))
                    const nextMax = Math.max(durationRange[1], newMin + 10000000)
                    setDurationRange([newMin, nextMax])
                  }}
                  className="w-full h-2 bg-sre-surface rounded-lg appearance-none cursor-pointer accent-sre-primary"
                />
              </div>
              <div>
                <label htmlFor="max-duration" className="text-xs text-sre-text-muted">Maximum Duration</label>
                <input
                  type="range"
                  min="0"
                  max="10000000000"
                  step="50000000"
                  value={durationRange[1]}
                  onChange={(e) => {
                    const newMax = Math.max(0, Number(e.target.value))
                    const nextMin = Math.min(durationRange[0], newMax - 10000000)
                    setDurationRange([Math.max(0, nextMin), newMax])
                  }}
                  className="w-full h-2 bg-sre-surface rounded-lg appearance-none cursor-pointer accent-sre-primary"
                />
              </div>
            </div>
            <div className="flex justify-between text-xs text-sre-text-muted mt-1">
              <span>0ms</span>
              <span>10s</span>
            </div>
            <button
              type="button"
              onClick={() => setDurationRange([DEFAULT_DURATION_RANGE.min, DEFAULT_DURATION_RANGE.max])}
              className="text-xs text-sre-primary hover:underline mt-1"
            >
              Reset range
            </button>
          </div>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => {
              setService('')
              setOperation('')
              setDurationRange([DEFAULT_DURATION_RANGE.min, DEFAULT_DURATION_RANGE.max])
              setStatusFilter('all')
            }}>
              Clear Filters
            </Button>
            <Button type="submit" loading={loading}>
              <span className="material-icons text-sm mr-2">search</span> Search Traces
            </Button>
          </div>
        </form>
      </Card>

      {viewMode === 'graph' && filteredTraces?.length > 0 && (
        <div className="mb-6">
          <ServiceGraph traces={filteredTraces} />
        </div>
      )}

      <Card
        title="Trace Results"
        subtitle={filteredTraces.length ? `Found ${filteredTraces.length} traces` : 'Run a search to see results'}
      >
        {(() => {
          if (loading) {
            return (
              <div className="py-12">
                <Spinner size="lg" />
              </div>
            );
          } else if (filteredTraces.length) {
            return (
              <div className="space-y-2">
                {filteredTraces.map((t) => {
                  const rootSpan = t.spans?.find(s => !s.parentSpanId && !s.parentSpanID) || t.spans?.[0]
                  const duration = rootSpan?.duration || 0
                  const hasError = t.spans?.some(hasSpanError)
                  const allServices = t.spans?.map(s => getServiceName(s)).filter(Boolean) || []
                  const serviceCount = new Set(allServices).size
                  const rootServiceName = rootSpan ? getServiceName(rootSpan) : 'unknown'

                  const traceId = t.traceID || t.traceId

                  return (
                    <button
                      key={traceId}
                      onClick={() => handleTraceClick(traceId)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleTraceClick(traceId);
                        }
                      }}
                      className="p-4 bg-sre-surface/50 border border-sre-border rounded-lg hover:border-sre-primary/50 transition-all cursor-pointer group w-full text-left"
                      type="button"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-3 mb-2">
                            <span className="material-icons text-sre-primary group-hover:scale-110 transition-transform">
                              {hasError ? 'error' : 'check_circle'}
                            </span>
                            <span className="font-mono text-sm text-sre-text font-semibold">
                              {traceId?.substring(0, 16)}...
                            </span>
                            <Badge variant={hasError ? 'error' : 'success'}>
                              {hasError ? 'ERROR' : 'OK'}
                            </Badge>
                            <Badge variant="info">{t.spans?.length || 0} spans</Badge>
                            <Badge variant="default">{serviceCount} services</Badge>
                          </div>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                            <div>
                              <span className="text-sre-text-muted">Service: </span>
                              <span className="text-sre-text font-semibold">{rootServiceName}</span>
                            </div>
                            {rootSpan?.operationName && (
                              <div>
                                <span className="text-sre-text-muted">Operation: </span>
                                <span className="text-sre-text font-semibold">{rootSpan.operationName}</span>
                              </div>
                            )}
                            <div>
                              <span className="text-sre-text-muted">Duration: </span>
                              <span className="text-sre-text font-semibold font-mono">{formatDuration(duration)}</span>
                            </div>
                            <div>
                              <span className="text-sre-text-muted">Started: </span>
                              <span className="text-sre-text font-semibold">
                                {new Date(rootSpan?.startTime / 1000).toLocaleTimeString()}
                              </span>
                            </div>
                          </div>
                        </div>
                        <span className="material-icons text-sre-text-muted group-hover:text-sre-primary transition-colors">
                          chevron_right
                        </span>
                      </div>
                    </button>
                  )
                })}
              </div>
            );
          } else {
            return (
              <div className="text-center py-12">
                <span className="material-icons text-6xl text-sre-text-subtle mb-4">timeline</span>
                <p className="text-sre-text-muted mb-4">No traces found. Try adjusting your search criteria or time range.</p>
              </div>
            );
          }
        })()}
      </Card>

      {selectedTrace && (
        <TraceTimeline trace={selectedTrace} onClose={() => setSelectedTrace(null)} />
      )}
    </div>
  )
}
