`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { useEffect, useState, useMemo, useCallback } from 'react'
import { useAutoRefresh } from '../hooks'
import PageHeader from '../components/ui/PageHeader'
import AutoRefreshControl from '../components/ui/AutoRefreshControl'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../contexts/ToastContext'
import { fetchTempoServices, searchTraces, getTrace } from '../api'
import { Card, Button, Select, Input, Alert, Badge, Spinner } from '../components/ui'
import ServiceGraph from '../components/tempo/ServiceGraph'
import TraceTimeline from '../components/tempo/TraceTimeline'
import { formatDuration } from '../utils/formatters'
import { getServiceName, hasSpanError } from '../utils/helpers'
import { TIME_RANGES, DEFAULT_DURATION_RANGE, TRACE_STATUS_OPTIONS, REFRESH_INTERVALS } from '../utils/constants'
import HelpTooltip from '../components/HelpTooltip'
import { discoverServices, computeTraceStats } from '../utils/tempoTraceUtils'

export default function TempoPage() {
  const [services, setServices] = useState([])
  const [service, setService] = useState('')
  const [operation, setOperation] = useState('')
  const [traceIdSearch, setTraceIdSearch] = useState('')
  const [durationRange, setDurationRange] = useState([DEFAULT_DURATION_RANGE.min, DEFAULT_DURATION_RANGE.max])
  const [statusFilter, setStatusFilter] = useState('all')
  const [timeRange, setTimeRange] = useState(60)
  const [traces, setTraces] = useState(null)
  const [selectedTrace, setSelectedTrace] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [viewMode, setViewMode] = useState('list')
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [refreshInterval, setRefreshInterval] = useState(30)

  const { isAuthenticated, loading: authLoading } = useAuth()
  const toast = useToast()

  const loadServices = useCallback(async () => {
    try {
      const data = await fetchTempoServices()
      setServices(data || [])
    } catch {
      setServices([])
    }
  }, [])

  // Load services only after authentication is ready
  useEffect(() => {
    if (isAuthenticated && !authLoading) {
      loadServices()
    }
  }, [isAuthenticated, authLoading, loadServices])

  // centralized auto-refresh hook (keeps previous behavior)
  useAutoRefresh(() => onSearch(), refreshInterval * 1000, autoRefresh)

  // If backend doesn't return services, derive them from loaded traces
  useEffect(() => {
    if (!services.length && traces?.data?.length) {
      const discovered = discoverServices(traces.data)
      if (discovered.length) setServices(discovered)
    }
  }, [traces, services.length])

  const handleTraceClick = useCallback(async (traceId) => {
    try {
      const trace = await getTrace(traceId)
      if (trace?.spans) {
        setSelectedTrace({
          ...trace,
          spans: trace.spans.map(s => ({
            ...s,
            endTime: s.startTime + (s.duration || 0)
          }))
        })
      } else {
        setError('Trace data is incomplete — no spans returned')
      }
    } catch (e) {
      setError(`Failed to load trace: ${e.message}`)
    }
  }, [])

  async function onSearch(e) {
    if (e) e.preventDefault()
    setError(null)

    // Direct trace ID lookup
    if (traceIdSearch.trim()) {
      setLoading(true)
      try {
        await handleTraceClick(traceIdSearch.trim())
      } finally {
        setLoading(false)
      }
      return
    }

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

      if (!services.length && res?.data?.length) {
        const discovered = discoverServices(res.data)
        if (discovered.length) setServices(discovered)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const filteredTraces = useMemo(() => {
    if (!traces?.data) return []
    return traces.data.filter(trace => {
      if (statusFilter === 'error') return trace.spans?.some(hasSpanError)
      if (statusFilter === 'ok') return !trace.spans?.some(hasSpanError)
      return true
    })
  }, [traces, statusFilter])

  const traceStats = useMemo(() => {
    return computeTraceStats(filteredTraces)
  }, [filteredTraces])

  function clearFilters() {
    setService('')
    setOperation('')
    setTraceIdSearch('')
    setDurationRange([DEFAULT_DURATION_RANGE.min, DEFAULT_DURATION_RANGE.max])
    setStatusFilter('all')
  }

  return (
    <div className="animate-fade-in">
      <PageHeader icon="timeline" title="Tracing" subtitle="Search and analyze distributed traces across your services">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            {[
              { key: 'list', icon: 'list', label: 'List View' },
              { key: 'graph', icon: 'hub', label: 'Dependency Map' },
            ].map(v => (
              <button
                key={v.key}
                onClick={() => setViewMode(v.key)}
                title={v.label}
                className={`px-3 py-2 rounded-lg transition-colors flex items-center gap-1.5 text-sm ${
                  viewMode === v.key
                    ? 'bg-sre-primary text-white shadow-sm'
                    : 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface'
                }`}
              >
                <span className="material-icons text-sm">{v.icon}</span>
                <span className="hidden sm:inline">{v.label}</span>
              </button>
            ))}
            <HelpTooltip text="Switch between list view (detailed trace information) and dependency map (service relationships)." />
          </div>

          <AutoRefreshControl
            enabled={autoRefresh}
            onToggle={setAutoRefresh}
            interval={refreshInterval}
            onIntervalChange={setRefreshInterval}
            intervalOptions={REFRESH_INTERVALS.slice(0,4)}
          />
        </div>
      </PageHeader>

      {error && (
        <Alert variant="error" className="mb-6" onClose={() => setError(null)}>
          <strong>Error:</strong> {error}
        </Alert>
      )}

      {/* Stats Bar */}
      {traceStats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          {[
            { label: 'Total Traces', value: traceStats.total, color: 'text-sre-text' },
            { label: 'Avg Duration', value: formatDuration(traceStats.avgDuration), color: 'text-sre-text' },
            { label: 'Max Duration', value: formatDuration(traceStats.maxDuration), color: 'text-sre-text' },
            { label: 'Error Rate', value: `${traceStats.errorRate.toFixed(1)}%`, color: traceStats.errorRate > 5 ? 'text-red-500' : 'text-green-500' },
            { label: 'Errors', value: traceStats.errorCount, color: traceStats.errorCount > 0 ? 'text-red-500' : 'text-green-500' },
          ].map(stat => (
            <Card key={stat.label} className="p-4 relative overflow-visible bg-gradient-to-br from-sre-surface to-sre-surface/80 border-2 border-sre-border/50 hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm">
              <div className="text-sre-text-muted text-xs mb-1">{stat.label}</div>
              <div className={`text-2xl font-bold ${stat.color}`}>{stat.value}</div>
            </Card>
          ))}
        </div>
      )}

      {/* Search Form */}
      <Card title="Search Traces" subtitle="Query traces by service, operation, duration, or trace ID" className="mb-6">
        <form onSubmit={onSearch} className="space-y-4">
          {/* Trace ID quick search */}
          <div className="flex gap-2 items-end pb-3 border-b border-sre-border">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <Input
                  size="sm"
                  label="Trace ID (direct lookup)"
                  value={traceIdSearch}
                  onChange={(e) => setTraceIdSearch(e.target.value)}
                  placeholder="Paste a trace ID to jump directly to it"
                  className="flex-1 px-2 py-0.5 text-sm"
                />
                <HelpTooltip text="Enter a specific trace ID to view that trace directly, bypassing the search filters." />
              </div>
            </div>
            <Button size="sm" type="submit" loading={loading && !!traceIdSearch.trim()} disabled={!traceIdSearch.trim() && loading}>
              <span className="material-icons text-xs mr-1">search</span> Lookup
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div>
              <div className="flex items-center gap-2">
                <Select
                  size="sm"
                  label="Service"
                  value={service}
                  onChange={(e) => setService(e.target.value)}
                  className="flex-1 px-2 py-0.5 text-sm"
                >
                  <option value="">All Services</option>
                  {services.length > 0 ? (
                    services.map((s) => <option key={s} value={s}>{s}</option>)
                  ) : (
                    <option disabled>No services discovered yet</option>
                  )}
                </Select>
                <HelpTooltip text="Filter traces by the service that initiated them. Services are automatically discovered from your traces." />
              </div>
            </div>

            <div>
              <div className="flex items-center gap-2">
                <Input
                  size="sm"
                  label="Operation"
                  value={operation}
                  onChange={(e) => setOperation(e.target.value)}
                  placeholder="e.g., HTTP GET /api"
                  className="flex-1 px-2 py-0.5 text-sm"
                />
                <HelpTooltip text="Filter traces by operation name, such as HTTP methods or function names." />
              </div>
            </div>

            <div>
              <div className="flex items-center gap-2">
                <Select
                  size="sm"
                  label="Time Range"
                  value={timeRange}
                  onChange={(e) => setTimeRange(Number(e.target.value))}
                  className="flex-1 px-2 py-0.5 text-sm"
                >
                  {TIME_RANGES.map(tr => (
                    <option key={tr.value} value={tr.value}>{tr.label}</option>
                  ))}
                </Select>
                <HelpTooltip text="Select how far back to search for traces. Larger ranges may take longer to query." />
              </div>
            </div>

            <div>
              <div className="flex items-center gap-2">
                <Select
                  size="sm"
                  label="Status"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="flex-1 px-2 py-0.5 text-sm"
                >
                  {TRACE_STATUS_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </Select>
                <HelpTooltip text="Filter traces by their status: all, successful, or those containing errors." />
              </div>
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2 mb-1">
              <label className="block text-xs font-medium text-sre-text">
                <span className="material-icons text-xs mr-1 align-middle">schedule</span>
                Duration Range: {formatDuration(durationRange[0])} – {formatDuration(durationRange[1])}
              </label>
              <HelpTooltip text="Filter traces by their total duration using the sliders below." />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-sre-text-muted">Minimum</label>
                <input
                  type="range" min="0" max="10000000000" step="50000000"
                  value={durationRange[0]}
                  onChange={(e) => {
                    const newMin = Math.max(0, Number(e.target.value))
                    setDurationRange([newMin, Math.max(durationRange[1], newMin + 10000000)])
                  }}
                  className="w-full h-1.5 bg-sre-surface rounded-lg appearance-none cursor-pointer accent-sre-primary"
                />
              </div>
              <div>
                <label className="text-xs text-sre-text-muted">Maximum</label>
                <input
                  type="range" min="0" max="10000000000" step="50000000"
                  value={durationRange[1]}
                  onChange={(e) => {
                    const newMax = Math.max(0, Number(e.target.value))
                    setDurationRange([Math.max(0, Math.min(durationRange[0], newMax - 10000000)), newMax])
                  }}
                  className="w-full h-1.5 bg-sre-surface rounded-lg appearance-none cursor-pointer accent-sre-primary"
                />
              </div>
            </div>
            <div className="flex justify-between text-xs text-sre-text-muted mt-0.5">
              <span>0ms</span>
              <button
                type="button"
                onClick={() => setDurationRange([DEFAULT_DURATION_RANGE.min, DEFAULT_DURATION_RANGE.max])}
                className="text-sre-primary hover:underline text-xs"
              >
                Reset range
              </button>
              <span>10s</span>
            </div>
          </div>

          <div className="flex justify-end gap-2 mt-2">
            <div className="flex items-center gap-2">
              <Button type="button" size="sm" variant="ghost" onClick={clearFilters}>
                Clear Filters
              </Button>
              <HelpTooltip text="Reset all search filters and duration range to their default values." />
            </div>
            <Button type="submit" size="sm" loading={loading && !traceIdSearch.trim()}>
              <span className="material-icons text-xs mr-1">search</span> Search Traces
            </Button>
          </div>
        </form>
      </Card>

      {/* Service Dependency Graph */}
      {viewMode === 'graph' && (
        <Card
          title="Dependency Map"
          subtitle={filteredTraces.length ? `Showing relationships between ${new Set(filteredTraces.flatMap(t => t.spans?.map(s => getServiceName(s)).filter(Boolean) || [])).size} services` : 'Run a search to see the dependency map'}
        >
          {filteredTraces.length > 0 ? (
            <ServiceGraph traces={filteredTraces} />
          ) : (
            <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
              <span className="material-icons text-5xl text-sre-text-muted mb-4 block">hub</span>
              <h3 className="text-xl font-semibold text-sre-text mb-2">No Traces Found</h3>
              <p className="text-sre-text-muted mb-6 text-sm max-w-md mx-auto">
                Try adjusting your search criteria, expanding the time range, or pasting a trace ID above. You also must select the right key to look at
              </p>
            </div>
          )}
        </Card>
      )}

      {/* Trace Results */}
      {viewMode === 'list' && (
        <Card
          title="Trace Results"
          subtitle={filteredTraces.length ? `Found ${filteredTraces.length} trace${filteredTraces.length === 1 ? '' : 's'}` : 'Run a search to see results'}
        >
          <div className="mb-4 flex items-center justify-between pb-4 border-b border-sre-border" />
          {loading ? (
            <div className="py-12 flex flex-col items-center">
              <Spinner size="lg" />
              <p className="text-sre-text-muted mt-4">Searching traces...</p>
            </div>
          ) : filteredTraces.length > 0 ? (
            <div className="space-y-2">
              {filteredTraces.map((t) => {
                const rootSpan = t.spans?.find(s => !s.parentSpanId && !s.parentSpanID) || t.spans?.[0]
                const duration = rootSpan?.duration || 0
                const traceHasError = t.spans?.some(hasSpanError)
                const allServices = t.spans?.map(s => getServiceName(s)).filter(Boolean) || []
                const serviceCount = new Set(allServices).size
                const rootServiceName = rootSpan ? getServiceName(rootSpan) : 'unknown'
                const traceId = t.traceID || t.traceId

                return (
                  <button
                    key={traceId}
                    onClick={() => handleTraceClick(traceId)}
                    className="p-4 bg-sre-surface/50 border border-sre-border rounded-lg hover:border-sre-primary/50 transition-all cursor-pointer group w-full text-left"
                    type="button"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-2">
                          <span className={`material-icons ${traceHasError ? 'text-red-500' : 'text-green-500'} group-hover:scale-110 transition-transform`}>
                            {traceHasError ? 'error' : 'check_circle'}
                          </span>
                          <span className="font-mono text-sm text-sre-text font-semibold">
                            {traceId?.substring(0, 16)}...
                          </span>
                          <Badge variant={traceHasError ? 'error' : 'success'}>
                            {traceHasError ? 'ERROR' : 'OK'}
                          </Badge>
                          <Badge variant="info">{t.spans?.length || 0} spans</Badge>
                          <Badge variant="default">{serviceCount} service{serviceCount !== 1 ? 's' : ''}</Badge>
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
          ) : (
            <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
              <span className="material-icons text-5xl text-sre-text-muted mb-4 block">timeline</span>
              <h3 className="text-xl font-semibold text-sre-text mb-2">No Traces Found</h3>
              <p className="text-sre-text-muted text-sm mb-6 max-w-md mx-auto">
                Try adjusting your search criteria, expanding the time range, or pasting a trace ID above. You also must select the right key to look at.
              </p>
            </div>
          )}
        </Card>
      )}

      {/* Trace Detail Modal */}
      {selectedTrace && (
        <TraceTimeline
          trace={selectedTrace}
          onClose={() => setSelectedTrace(null)}
          onCopyTraceId={() => {
            const id = selectedTrace.traceId || selectedTrace.traceID || selectedTrace.id || ''
            navigator.clipboard.writeText(id).then(
              () => toast.success('Trace ID copied'),
              () => toast.error('Failed to copy')
            )
          }}
        />
      )}
    </div>
  )
}
