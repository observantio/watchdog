/**
 * TraceTimeline component for visualizing trace spans
 * @module components/tempo/TraceTimeline
 */

import { useState, useMemo } from 'react'
import PropTypes from 'prop-types'
import { Badge, Button } from '../ui'
import { formatDuration } from '../../utils/formatters'
import { getServiceName, hasSpanError, getSpanColorClass } from '../../utils/helpers'

/**
 * Build a depth map for spans based on parent relationships
 */
function buildDepthMap(spans) {
  const idToSpan = new Map()
  spans.forEach(s => {
    const id = s.spanId || s.spanID
    if (id) idToSpan.set(id, s)
  })

  const depthCache = new Map()

  function getDepth(span) {
    const id = span.spanId || span.spanID
    if (depthCache.has(id)) return depthCache.get(id)

    const parentId = span.parentSpanId || span.parentSpanID
    if (!parentId || !idToSpan.has(parentId)) {
      depthCache.set(id, 0)
      return 0
    }
    const depth = getDepth(idToSpan.get(parentId)) + 1
    depthCache.set(id, depth)
    return depth
  }

  spans.forEach(s => getDepth(s))
  return depthCache
}

/**
 * TraceTimeline component
 */
export default function TraceTimeline({ trace, onClose, onCopyTraceId }) {
  const [showAllTags, setShowAllTags] = useState({})

  if (!trace || !trace.spans) return null

  const traceId = trace.traceId || trace.traceID || trace.id || ''

  // Handler to copy the full trace ID
  const handleCopyTraceId = () => {
    if (onCopyTraceId) {
      onCopyTraceId(traceId)
    } else if (navigator?.clipboard) {
      navigator.clipboard.writeText(traceId)
    }
  }

  const spansWithEndTime = useMemo(() => {
    const sorted = [...trace.spans].sort((a, b) => a.startTime - b.startTime)
    return sorted.map(s => ({
      ...s,
      endTime: s.startTime + (s.duration || 0),
      serviceName: getServiceName(s)
    }))
  }, [trace.spans])

  const { minTime, maxTime, totalDuration, depthMap } = useMemo(() => {
    const min = Math.min(...spansWithEndTime.map(s => s.startTime))
    const max = Math.max(...spansWithEndTime.map(s => s.endTime))
    const depths = buildDepthMap(spansWithEndTime)
    return { minTime: min, maxTime: max, totalDuration: max - min, depthMap: depths }
  }, [spansWithEndTime])

  const traceHasError = useMemo(
    () => spansWithEndTime.some(hasSpanError),
    [spansWithEndTime]
  )

  const serviceCount = useMemo(
    () => new Set(spansWithEndTime.map(s => s.serviceName)).size,
    [spansWithEndTime]
  )

  const getSpanPosition = (span) => {
    if (!totalDuration) return { left: '0%', width: '100%' }
    const start = ((span.startTime - minTime) / totalDuration) * 100
    const width = ((span.endTime - span.startTime) / totalDuration) * 100
    return { left: `${start}%`, width: `${Math.max(width, 0.5)}%` }
  }

  const toggleTags = (spanKey) => {
    setShowAllTags(prev => ({ ...prev, [spanKey]: !prev[spanKey] }))
  }

  const getTagEntries = (span) => {
    if (!span.tags) return []
    if (Array.isArray(span.tags)) {
      return span.tags.map((t, idx) => ({
        key: t?.key || t?.k || `tag${idx}`,
        value: t?.value ?? t?.v ?? t?.val ?? t
      }))
    }
    return Object.entries(span.tags).map(([key, value]) => ({ key, value }))
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
      <div className="bg-sre-bg w-full max-w-6xl max-h-[90vh] rounded-xl shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="bg-gradient-to-r from-sre-surface to-sre-surface/80 border-b border-sre-border px-6 py-4 flex items-center justify-between flex-shrink-0">
          <div>
            <h2 id={`trace-timeline-title-${traceId}`} className="text-xl font-bold text-sre-text flex items-center gap-2">
              <span className="material-icons text-sre-primary">timeline</span>
              Trace Timeline
            </h2>
            <div className="flex items-center gap-3 mt-2">
              <div className="flex items-center gap-2">
                <span className="text-sm text-sre-text-muted">ID:</span>
                <code className="text-sm text-sre-text font-mono bg-sre-bg px-2 py-1 rounded border">
                  {traceId.substring(0, 16)}...
                </code>
              </div>
              <button
                onClick={handleCopyTraceId}
                className="p-1.5 hover:bg-sre-bg-alt rounded-lg transition-colors group"
                title="Copy Trace ID"
              >
                <span className="material-icons text-sm text-sre-text-muted group-hover:text-sre-primary">content_copy</span>
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={traceHasError ? 'error' : 'success'} className="text-xs">
              {traceHasError ? 'ERROR' : 'OK'}
            </Badge>
            <button onClick={onClose} aria-label="Close dialog" className="p-2 hover:bg-sre-bg-alt rounded-lg transition-colors">
              <span className="material-icons text-sre-text-muted hover:text-sre-text">close</span>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto overflow-x-hidden flex-1">
          {/* Summary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="p-4 bg-gradient-to-br from-sre-surface to-sre-surface/80 border-2 border-sre-border/50 rounded-lg hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm">
              <div className="text-sre-text-muted text-xs mb-1 flex items-center gap-1">
                <span className="material-icons text-sm">schedule</span>
                Total Duration
              </div>
              <div className="text-xl font-bold text-sre-text">{formatDuration(totalDuration)}</div>
            </div>
            <div className="p-4 bg-gradient-to-br from-sre-surface to-sre-surface/80 border-2 border-sre-border/50 rounded-lg hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm">
              <div className="text-sre-text-muted text-xs mb-1 flex items-center gap-1">
                <span className="material-icons text-sm">call_split</span>
                Spans
              </div>
              <div className="text-xl font-bold text-sre-text">{spansWithEndTime.length}</div>
            </div>
            <div className="p-4 bg-gradient-to-br from-sre-surface to-sre-surface/80 border-2 border-sre-border/50 rounded-lg hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm">
              <div className="text-sre-text-muted text-xs mb-1 flex items-center gap-1">
                <span className="material-icons text-sm">hub</span>
                Services
              </div>
              <div className="text-xl font-bold text-sre-text">{serviceCount}</div>
            </div>
            <div className="p-4 bg-gradient-to-br from-sre-surface to-sre-surface/80 border-2 border-sre-border/50 rounded-lg hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm">
              <div className="text-sre-text-muted text-xs mb-1 flex items-center gap-1">
                <span className="material-icons text-sm">check_circle</span>
                Status
              </div>
              <Badge variant={traceHasError ? 'error' : 'success'} className="mt-1">
                {traceHasError ? 'ERROR' : 'OK'}
              </Badge>
            </div>
          </div>

          {/* Timeline Visualization */}
          <div className="bg-sre-surface/30 border border-sre-border rounded-lg p-4 mb-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-sre-text flex items-center gap-2">
                <span className="material-icons text-sre-primary">timeline</span>
                Span Timeline
              </h3>
              <div className="text-xs text-sre-text-muted">
                {formatDuration(totalDuration)} total
              </div>
            </div>

            {/* Time scale */}
            <div className="relative mb-4">
              <div className="h-px bg-sre-border"></div>
              <div className="flex justify-between text-xs text-sre-text-muted mt-1">
                <span>0ms</span>
                <span>{formatDuration(totalDuration)}</span>
              </div>
            </div>

            {/* Spans */}
            <div className="space-y-3">
              {spansWithEndTime.map((span, idx) => {
                const position = getSpanPosition(span)
                const duration = span.duration || 0
                const spanId = span.spanId || span.spanID || idx
                const depth = depthMap.get(spanId) || 0
                const isError = hasSpanError(span)
                const colorClass = getSpanColorClass(span.serviceName, isError)
                const tagEntries = getTagEntries(span)
                const showAll = showAllTags[spanId]
                const visibleTags = showAll ? tagEntries : tagEntries.slice(0, 3)

                return (
                  <div key={spanId} className="group relative bg-sre-surface/50 rounded-lg p-3 border border-sre-border/50 hover:border-sre-primary/30 transition-all duration-200">
                    {/* Span header */}
                    <div className="flex items-center gap-3 mb-2">
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        <div className={`w-3 h-3 rounded-full ${isError ? 'bg-red-500' : 'bg-green-500'} flex-shrink-0`}></div>
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-semibold text-sre-text truncate" title={span.operationName}>
                            {span.operationName}
                          </div>
                          <div className="text-xs text-sre-text-muted truncate flex items-center gap-1" title={span.serviceName}>
                            <span className="material-icons text-xs">dns</span>
                            {span.serviceName}
                          </div>
                        </div>
                      </div>

                      <div className="text-xs font-mono text-sre-text-muted bg-sre-surface px-2 py-1 rounded">
                        {formatDuration(duration)}
                      </div>
                    </div>

                    {/* Timeline bar */}
                    <div className="relative h-6 bg-sre-surface rounded border border-sre-border mb-2">
                      <div
                        className={`absolute top-0 h-full ${colorClass} rounded transition-all group-hover:brightness-110 shadow-sm`}
                        style={position}
                        title={`${span.operationName} — ${formatDuration(duration)}`}
                      />
                      {/* Depth indicator */}
                      {depth > 0 && (
                        <div className="absolute left-0 top-0 h-full w-1 bg-sre-primary/20 rounded-l"></div>
                      )}
                    </div>

                    {/* Tags */}
                    {tagEntries.length > 0 && (
                      <div className="flex flex-wrap gap-1 items-center">
                        {visibleTags.map((t, idx2) => (
                          <span
                            key={`${t.key}-${idx2}`}
                            className="text-xs px-2 py-1 bg-sre-surface border border-sre-border rounded text-sre-text-muted max-w-xs truncate hover:bg-sre-surface-light transition-colors"
                            title={`${t.key}: ${typeof t.value === 'object' ? JSON.stringify(t.value) : String(t.value)}`}
                          >
                            <span className="font-medium text-sre-primary">{t.key}:</span> {typeof t.value === 'object' ? JSON.stringify(t.value) : String(t.value)}
                          </span>
                        ))}
                        {tagEntries.length > 3 && (
                          <button
                            onClick={() => toggleTags(spanId)}
                            className="text-xs text-sre-primary hover:underline px-2 py-1"
                          >
                            {showAll ? 'Show less' : `+${tagEntries.length - 3} more`}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* Footer legend */}
        <div className="border-t border-sre-border px-6 py-4 bg-sre-surface/30 flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6 text-sm text-sre-text-muted">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-green-500"></div>
                <span>Success</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-red-500"></div>
                <span>Error</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-1 h-4 bg-sre-primary/20 rounded"></div>
                <span>Child span</span>
              </div>
              <div className="text-xs">
                Span colors are assigned by service • Indent depth reflects parent-child relationships
              </div>
            </div>
            <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
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
  onCopyTraceId: PropTypes.func,
}
