import { Card, Button, Select, Input } from '../ui'
import HelpTooltip from '../HelpTooltip'
import { formatDuration } from '../../utils/formatters'
import { TIME_RANGES, DEFAULT_DURATION_RANGE, TRACE_STATUS_OPTIONS } from '../../utils/constants'

export default function TempoSearchForm({
  traceIdSearch,
  setTraceIdSearch,
  service,
  setService,
  services,
  operation,
  setOperation,
  timeRange,
  setTimeRange,
  statusFilter,
  setStatusFilter,
  durationRange,
  setDurationRange,
  clearFilters,
  onSearch,
  loading
}) {
  return (
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
  )
}