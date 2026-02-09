import { Badge, Spinner } from '../../components/ui'
import PropTypes from 'prop-types'
import { formatNsToIso, formatRelativeTime, formatLogLine, getLogLevelColor, getLogLevelBadge } from '../../utils/logFormatters'

function normalizeStreamLabelValue(label, value) {
  if (typeof value !== 'string') return value
  if (!value.includes('="')) return value

  const escapedLabel = String(label).replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\\$&`)
  const matcher = new RegExp(`${escapedLabel}="([^"]+)"`)
  const match = matcher.exec(value)
  if (match?.[1]) return match[1]

  const cutIndex = value.indexOf('",')
  if (cutIndex > 0) return value.slice(0, cutIndex)

  return value
}

export default function LogResults({ queryResult, loading, filterDisplayedLogs, viewMode, expandedLogs, toggleLogExpand, copyToClipboard, handleTraceClick, handleStreamClick }) {
  if (loading) {
    return (
      <div className="py-12 flex flex-col items-center ">
        <Spinner size="lg" />
        <p className="text-sre-text-muted mt-4">Querying logs...</p>
      </div>
    )
  }

  if (!queryResult?.data?.result || queryResult.data.result.length === 0) {
    return (
      <div className="text-center py-16">
        <svg className="w-20 h-20 mx-auto text-sre-text-subtle mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <p className="text-lg text-sre-text-muted mb-2">No logs found</p>
        <p className="text-sm text-sre-text-subtle">Try adjusting your filters or expanding the time range</p>
      </div>
    )
  }

  return (
    <div className="space-y-4 overflow-auto p-3 scrollbar-thin h-[70rem]">
      {queryResult?.data?.result.map((stream, streamIdx) => {
        const filteredValues = filterDisplayedLogs(stream)
        if (!filteredValues || filteredValues.length === 0) return null

        const streamKey = stream.stream
          ? Object.entries(stream.stream).sort((a, b) => String(a[0]).localeCompare(String(b[0]))).map(([k, v]) => `${k}=${v}`).join('|')
          : `stream-${streamIdx}`

        return (
          <div key={streamKey} className="border border-sre-border rounded-lg overflow-hidden">
            <div className="bg-sre-bg-alt px-4 py-2 border-b border-sre-border">
              <div className="flex items-center justify-between">
                <div className="flex flex-wrap gap-2">
                  {stream.stream && Object.entries(stream.stream).map(([k, v]) => (
                    <span key={k} className="inline-flex items-center gap-1 px-2 py-0.5 bg-sre-surface border border-sre-border rounded text-xs font-mono">
                      <span className="text-sre-primary font-semibold">{k}</span>
                      <span className="text-sre-text-muted">=</span>
                      <span className="text-sre-text">{normalizeStreamLabelValue(k, v)}</span>
                    </span>
                  ))}
                </div>
                <Badge variant="secondary">{filteredValues.length}</Badge>
              </div>
            </div>

            <div className="divide-y divide-sre-border">
              {filteredValues.slice().reverse().slice(0, viewMode === 'compact' ? 200 : 100).map((v) => {
                const formatted = formatLogLine(v[1])
                const logKey = `${streamIdx}-${v[0]}-${String(v[1]).substring(0, 50).replaceAll(/[^a-zA-Z0-9]/g, '')}`
                const isExpanded = !!expandedLogs[logKey]
                const badge = getLogLevelBadge(v[1])

                let displayText
                if (isExpanded) {
                  displayText = formatted.data
                } else if (typeof formatted.data === 'string' && formatted.data.length > 300) {
                  displayText = formatted.data.substring(0, 300) + '...'
                } else {
                  displayText = formatted.data
                }

                if (viewMode === 'compact') {
                  return (
                    <div key={logKey} className="px-4 py-2 hover:bg-sre-surface/50 transition-colors text-xs font-mono">
                      <span className="text-sre-text-muted mr-3">{formatNsToIso(v[0]).substring(11,19)}</span>
                      <span className={`${badge.class} px-2 py-0.5 rounded text-[10px] font-bold mr-2`}>{badge.text}</span>
                      <span className={getLogLevelColor(v[1])}>{String(v[1]).substring(0, 150)}{String(v[1]).length > 150 ? '...' : ''}</span>
                    </div>
                  )
                }

                if (viewMode === 'raw') {
                  return (
                    <div key={logKey} className="px-4 py-2 hover:bg-sre-surface/50 transition-colors">
                      <pre className="text-xs font-mono text-sre-text whitespace-pre-wrap break-all">{JSON.stringify({timestamp: v[0], log: v[1]}, null, 2)}</pre>
                    </div>
                  )
                }

                return (
                  <div key={logKey} className="px-4 py-3 hover:bg-sre-surface/50 transition-colors">
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <span className={`${badge.class} px-2 py-1 rounded text-[10px] font-bold border`}>{badge.text}</span>
                        <div className="text-xs text-sre-text-muted">
                          <div className="font-semibold">{formatNsToIso(v[0])}</div>
                          <div className="text-[10px]">{formatRelativeTime(v[0])}</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button onClick={() => copyToClipboard(v[1])} className="p-1 hover:bg-sre-bg-alt rounded text-sre-text-muted hover:text-sre-text" title="Copy log">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
                        </button>
                        {formatted.type === 'json' && (
                          <button onClick={() => toggleLogExpand(logKey)} className="p-1 hover:bg-sre-bg-alt rounded text-sre-text-muted hover:text-sre-text">
                            <svg className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7"/></svg>
                          </button>
                        )}
                      </div>
                    </div>

                    {formatted.type === 'json' ? (
                      <div className="mt-2 space-y-1">
                        {Object.entries(formatted.data).slice(0, isExpanded ? undefined : 5).map(([key, val]) => (
                          <div key={key} className="flex gap-3 text-sm">
                            <span className="text-sre-primary font-semibold min-w-[120px] font-mono">{key}:</span>
                            <span className={`${getLogLevelColor(String(val))} flex-1 font-mono break-all`}>{typeof val === 'object' ? JSON.stringify(val) : String(val)}</span>
                          </div>
                        ))}
                        {!isExpanded && Object.keys(formatted.data).length > 5 && (
                          <button onClick={() => toggleLogExpand(logKey)} className="text-xs text-sre-primary hover:underline mt-2">Show {Object.keys(formatted.data).length - 5} more fields...</button>
                        )}
                      </div>
                    ) : (
                      <div className={`mt-2 text-sm font-mono ${getLogLevelColor(formatted.data)} break-all`}>
                        {displayText}
                        {!isExpanded && formatted.data.length > 300 && (
                          <button onClick={() => toggleLogExpand(logKey)} className="text-xs text-sre-primary hover:underline ml-2">Show more</button>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

LogResults.propTypes = {
  queryResult: PropTypes.object,
  loading: PropTypes.bool,
  filterDisplayedLogs: PropTypes.func.isRequired,
  viewMode: PropTypes.string,
  expandedLogs: PropTypes.object,
  toggleLogExpand: PropTypes.func.isRequired,
  copyToClipboard: PropTypes.func.isRequired,
  handleTraceClick: PropTypes.func,
  handleStreamClick: PropTypes.func,
}
