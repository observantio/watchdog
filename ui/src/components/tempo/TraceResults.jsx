import PropTypes from 'prop-types'
import { FixedSizeList as List } from 'react-window'
import { Badge } from '../ui'
import { formatDuration, formatNsToIso, formatRelativeTime } from '../../utils/formatters'
import { getServiceName, hasSpanError } from '../../utils/helpers'

function TraceRow({ index, style, data }) {
  const { traces, handleTraceClick, viewMode } = data
  const t = traces[index]
  const rootSpan = t.spans?.find(s => !s.parentSpanId && !s.parentSpanID) || t.spans?.[0]
  const duration = rootSpan?.duration || 0
  const traceHasError = t.spans?.some(hasSpanError)
  const allServices = t.spans?.map(s => getServiceName(s)).filter(Boolean) || []
  const serviceCount = new Set(allServices).size
  const rootServiceName = rootSpan ? getServiceName(rootSpan) : 'unknown'
  const traceId = t.traceID || t.traceId

  return (
    <div style={style} className="p-4 bg-sre-surface/50 border-b border-sre-border group w-full text-left cursor-pointer">
      <button
        onClick={() => handleTraceClick(traceId)}
        type="button"
        className="w-full text-left flex items-start justify-between"
      >
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            <span className={`material-icons ${traceHasError ? 'text-red-500' : 'text-green-500'} group-hover:scale-110 transition-transform`}>{traceHasError ? 'error' : 'check_circle'}</span>
            <span className="font-mono text-sm text-sre-text font-semibold">{traceId?.substring(0, 16)}...</span>
            <Badge variant={traceHasError ? 'error' : 'success'}>{traceHasError ? 'ERROR' : 'OK'}</Badge>
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
              <span className="text-sre-text font-semibold">{new Date(rootSpan?.startTime / 1000).toLocaleTimeString()}</span>
            </div>
          </div>
        </div>
        <span className="material-icons text-sre-text-muted group-hover:text-sre-primary transition-colors">chevron_right</span>
      </button>
    </div>
  )
}

TraceRow.propTypes = {
  index: PropTypes.number.isRequired,
  style: PropTypes.object.isRequired,
  data: PropTypes.object.isRequired,
}

export default function TraceResults({ traces, loading, handleTraceClick, viewMode = 'list' }) {
  if (loading) {
    return (
      <div className="py-12 flex flex-col items-center">
        <div className="loader" />
        <p className="text-sre-text-muted mt-4">Searching traces...</p>
      </div>
    )
  }

  if (!traces || traces.length === 0) {
    return (
      <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
        <span className="material-icons text-5xl text-sre-text-muted mb-4 block">timeline</span>
        <h3 className="text-xl font-semibold text-sre-text mb-2">No Traces Found</h3>
        <p className="text-sre-text-muted text-sm mb-6 max-w-md mx-auto">Try adjusting your search criteria, expanding the time range, or pasting a trace ID above.</p>
      </div>
    )
  }

  const itemSize = 120
  const height = Math.min(traces.length, 12) * itemSize

  return (
    <div>
      <List
        height={height}
        itemCount={traces.length}
        itemSize={itemSize}
        width="100%"
        itemData={{ traces, handleTraceClick, viewMode }}
      >
        {TraceRow}
      </List>
    </div>
  )
}

TraceResults.propTypes = {
  traces: PropTypes.arrayOf(PropTypes.object).isRequired,
  loading: PropTypes.bool,
  handleTraceClick: PropTypes.func.isRequired,
  viewMode: PropTypes.string,
}
