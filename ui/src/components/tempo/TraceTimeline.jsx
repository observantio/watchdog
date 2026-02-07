/**
 * TraceTimeline component for visualizing trace spans
 * @module components/tempo/TraceTimeline
 */

import PropTypes from 'prop-types'
import { Badge } from '../ui'
import { formatDuration } from '../../utils/formatters'
import { getServiceName } from '../../utils/helpers'

/**
 * TraceTimeline component
 * @param {object} props - Component props
 * @param {object} props.trace - Trace object with spans
 * @param {Function} props.onClose - Close handler function
*/

export default function TraceTimeline({ trace, onClose }) {
  if (!trace || !trace.spans) return null

  const traceId = trace.traceId || trace.traceID || trace.id || ''

  const spans = [...trace.spans].sort((a, b) => a.startTime - b.startTime)
  const spansWithEndTime = spans.map(s => ({
    ...s,
    endTime: s.startTime + (s.duration || 0),
    serviceName: getServiceName(s)
  }))
  const minTime = Math.min(...spansWithEndTime.map(s => s.startTime))
  const maxTime = Math.max(...spansWithEndTime.map(s => s.endTime))
  const totalDuration = maxTime - minTime

  const getSpanPosition = (span) => {
    const start = ((span.startTime - minTime) / totalDuration) * 100
    const width = ((span.endTime - span.startTime) / totalDuration) * 100
    return { left: `${start}%`, width: `${Math.max(width, 0.5)}%` }
  }

  const getSpanColor = (span) => {
    const hasError = span.tags?.find(t => t.key === 'error' && t.value === true) || span.status?.code === 'ERROR'
    if (hasError) return 'bg-red-500'
    if (span.serviceName?.includes('payment')) return 'bg-green-500'
    if (span.serviceName?.includes('api')) return 'bg-blue-500'
    if (span.serviceName?.includes('frontend')) return 'bg-purple-500'
    return 'bg-sre-primary'
  }

  return (
    <div
      className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4 animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-labelledby={`trace-timeline-title-${traceId}`}
      tabIndex={-1}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
      onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}
    >
      <div className="bg-sre-bg w-full max-w-6xl max-h-[90vh] rounded-xl shadow-2xl overflow-hidden">
        <div className="bg-sre-surface border-b border-sre-border px-6 py-4 flex items-center justify-between">
          <div>
            <h2 id={`trace-timeline-title-${traceId}`} className="text-xl font-bold text-sre-text flex items-center gap-2">
              <span className="material-icons text-sre-primary">timeline</span>{' '}
              Trace Timeline
            </h2>
            <p className="text-sm text-sre-text-muted font-mono mt-1">ID: {traceId}</p>
          </div>
          <button onClick={onClose} aria-label="Close dialog" className="p-2 hover:bg-sre-bg-alt rounded-lg transition-colors">
            <span className="material-icons text-sre-text-muted hover:text-sre-text">close</span>
          </button>
        </div>

        <div className="p-6 overflow-y-auto overflow-x-hidden max-h-[calc(90vh-80px)]">
          <div className="bg-sre-surface/50 border border-sre-border rounded-lg p-4 mb-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <div className="text-sre-text-muted mb-1">Total Duration</div>
                <div className="text-lg font-bold text-sre-text">{formatDuration(totalDuration)}</div>
              </div>
              <div>
                <div className="text-sre-text-muted mb-1">Spans</div>
                <div className="text-lg font-bold text-sre-text">{spans.length}</div>
              </div>
              <div>
                <div className="text-sre-text-muted mb-1">Services</div>
                <div className="text-lg font-bold text-sre-text">
                  {new Set(spans.map(s => s.serviceName)).size}
                </div>
              </div>
              <div>
                <div className="text-sre-text-muted mb-1">Status</div>
                <Badge variant={spans.some(s => s.tags?.find(t => t.key === 'error' && t.value === true) || s.status?.code === 'ERROR') ? 'error' : 'success'}>
                  {spans.some(s => s.tags?.find(t => t.key === 'error' && t.value === true) || s.status?.code === 'ERROR') ? 'ERROR' : 'OK'}
                </Badge>
              </div>
            </div>
          </div>

          <div className="space-y-2">
            {spansWithEndTime.map((span, idx) => {
              const position = getSpanPosition(span)
              const duration = span.duration || 0
              const depth = span.parentSpanId || span.parentSpanID ?
                spansWithEndTime.findIndex(s => (s.spanId || s.spanID) === (span.parentSpanId || span.parentSpanID)) + 1 : 0

              return (
                <div key={span.spanId || span.spanID || idx} className="group relative" style={{ paddingLeft: `${depth * 20}px` }}>
                  <div className="flex items-center gap-3">
                    <div className="min-w-[160px] max-w-[220px] break-words whitespace-normal">
                      <div className="text-sm font-semibold text-sre-text break-words whitespace-normal">{span.operationName}</div>
                      <div className="text-xs text-sre-text-muted break-words whitespace-normal">{span.serviceName}</div>
                    </div>

                    <div className="flex-1 relative h-8 bg-sre-surface rounded border border-sre-border">
                      <div
                        className={`absolute top-0 h-full ${getSpanColor(span)} rounded transition-all group-hover:opacity-80`}
                        style={position}
                        title={`${span.operationName} - ${formatDuration(duration)}`}
                      />
                    </div>

                    <div className="min-w-[80px] text-right text-xs font-mono text-sre-text-muted">
                      {formatDuration(duration)}
                    </div>
                  </div>

                  {span.tags && (
                    <div className="ml-[220px] mt-1 flex flex-wrap gap-1">
                      {Array.isArray(span.tags)
                        ? span.tags.slice(0, 5).map((t, idx2) => {
                          const k = t?.key || t?.k || `tag${idx2}`
                          const v = t?.value ?? t?.v ?? t?.val ?? t
                          return (
                            <span key={k + idx2} className="text-[10px] px-2 py-0.5 bg-sre-surface border border-sre-border rounded text-sre-text-muted break-words whitespace-normal" style={{ maxWidth: 'calc(100% - 240px)' }}>
                              {k}: {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                            </span>
                          )
                        })
                        : Object.entries(span.tags).slice(0, 5).map(([key, value]) => (
                          <span key={key} className="text-[10px] px-2 py-0.5 bg-sre-surface border border-sre-border rounded text-sre-text-muted break-words whitespace-normal" style={{ maxWidth: 'calc(100% - 240px)' }}>
                            {key}: {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                          </span>
                        ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

TraceTimeline.propTypes = {
  trace: PropTypes.shape({
    traceId: PropTypes.string,
    traceID: PropTypes.string,
    id: PropTypes.string,
    spans: PropTypes.arrayOf(PropTypes.object).isRequired,
  }),
  onClose: PropTypes.func.isRequired,
}
