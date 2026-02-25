import PropTypes from 'prop-types'
import Section from './Section'

function severityClass(severity) {
  if (severity === 'critical' || severity === 'high') return 'text-red-300'
  if (severity === 'medium') return 'text-amber-300'
  return 'text-emerald-300'
}

function asTime(timestamp) {
  const value = Number(timestamp || 0)
  if (!Number.isFinite(value) || value <= 0) return '-'
  return new Date(value * 1000).toLocaleTimeString()
}

function DataSection({ title, count, columns, rows, rowKey, renderRow, empty }) {
  return (
    <div className="border border-sre-border rounded-xl bg-sre-surface/20 overflow-hidden">
      <div className="px-3 py-2 border-b border-sre-border bg-sre-surface/40 flex items-center justify-between">
        <h4 className="text-sm font-semibold text-sre-text">{title}</h4>
        <span className="text-[11px] text-sre-text-muted">{count}</span>
      </div>
      {rows.length === 0 ? (
        <p className="p-4 text-xs text-sre-text-muted">{empty}</p>
      ) : (
        <div className="max-h-[250px] overflow-auto scrollbar-thin scrollbar-thumb-sre-border scrollbar-track-transparent">
          <table className="min-w-full text-left text-xs">
            <thead className="sticky top-0 bg-sre-surface/85 backdrop-blur-sm">
              <tr className="text-sre-text-muted uppercase tracking-wide">
                {columns.map((column) => (
                  <th key={column} className="px-3 py-2">{column}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-sre-border/40">
              {rows.map((row, index) => (
                <tr key={rowKey(row, index)} className="hover:bg-sre-surface/35">
                  {renderRow(row, index)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

DataSection.propTypes = {
  title: PropTypes.string.isRequired,
  count: PropTypes.number.isRequired,
  columns: PropTypes.arrayOf(PropTypes.string).isRequired,
  rows: PropTypes.array.isRequired,
  rowKey: PropTypes.func.isRequired,
  renderRow: PropTypes.func.isRequired,
  empty: PropTypes.string.isRequired,
}

export default function RcaAnomalyPanels({ report, compact = false }) {
  const metricAnomalies = (report?.metric_anomalies || []).slice(0, 250)
  const logBursts = (report?.log_bursts || []).slice(0, 250)
  const logPatterns = (report?.log_patterns || []).slice(0, 250)
  const serviceLatency = (report?.service_latency || []).slice(0, 250)
  const errorPropagation = (report?.error_propagation || []).slice(0, 250)

  const inner = (
    <>
      <h3 className="text-lg text-sre-text font-semibold mb-3">Anomalies and Signals</h3>
      <div className={compact ? 'grid grid-cols-1 gap-3' : 'grid grid-cols-1 xl:grid-cols-2 gap-3'}>
        <DataSection
          title="Metric Anomalies"
          count={metricAnomalies.length}
          columns={['Metric', 'Time', 'Value', 'Z-Score', 'Severity']}
          rows={metricAnomalies}
          rowKey={(row, index) => `${row.metric_name}-${row.timestamp}-${index}`}
          empty="No metric anomalies."
          renderRow={(row) => (
            <>
              <td className="px-3 py-2 text-sre-text">{row.metric_name || '-'}</td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">{asTime(row.timestamp)}</td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">{Number(row.value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">{Number(row.z_score || 0).toFixed(2)}</td>
              <td className={`px-3 py-2 uppercase ${severityClass(row.severity)}`}>{row.severity || '-'}</td>
            </>
          )}
        />

        <DataSection
          title="Log Bursts"
          count={logBursts.length}
          columns={['Window', 'Rate/s', 'Baseline', 'Ratio', 'Severity']}
          rows={logBursts}
          rowKey={(row, index) => `${row.window_start}-${row.window_end}-${index}`}
          empty="No log bursts."
          renderRow={(row) => (
            <>
              <td className="px-3 py-2 text-sre-text-muted">{asTime(row.window_start)} - {asTime(row.window_end)}</td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">{Number(row.rate_per_second || 0).toFixed(2)}</td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">{Number(row.baseline_rate || 0).toFixed(2)}</td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">{Number(row.ratio || 0).toFixed(2)}</td>
              <td className={`px-3 py-2 uppercase ${severityClass(row.severity)}`}>{row.severity || '-'}</td>
            </>
          )}
        />

        <DataSection
          title="Log Patterns"
          count={logPatterns.length}
          columns={['Pattern', 'Count', 'Rate/min', 'Severity']}
          rows={logPatterns}
          rowKey={(row, index) => `${row.pattern}-${row.first_seen}-${index}`}
          empty="No log patterns."
          renderRow={(row) => (
            <>
              <td className="px-3 py-2 text-sre-text truncate max-w-[270px]" title={row.pattern || ''}>{row.pattern || '-'}</td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">{row.count || 0}</td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">{Number(row.rate_per_minute || 0).toFixed(2)}</td>
              <td className={`px-3 py-2 uppercase ${severityClass(row.severity)}`}>{row.severity || '-'}</td>
            </>
          )}
        />

        <DataSection
          title="Service Latency"
          count={serviceLatency.length}
          columns={['Service', 'Operation', 'P95 ms', 'P99 ms', 'Apdex']}
          rows={serviceLatency}
          rowKey={(row, index) => `${row.service}-${row.operation}-${index}`}
          empty="No latency outliers."
          renderRow={(row) => (
            <>
              <td className="px-3 py-2 text-sre-text">{row.service || '-'}</td>
              <td className="px-3 py-2 text-sre-text-muted">{row.operation || '-'}</td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">{Number(row.p95_ms || 0).toFixed(1)}</td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">{Number(row.p99_ms || 0).toFixed(1)}</td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">{Number(row.apdex || 0).toFixed(3)}</td>
            </>
          )}
        />
      </div>

      <div className="mt-3 border border-sre-border rounded-xl bg-sre-surface/20 overflow-hidden">
        <div className="px-3 py-2 border-b border-sre-border bg-sre-surface/40 flex items-center justify-between">
          <h4 className="text-sm font-semibold text-sre-text">Error Propagation</h4>
          <span className="text-[11px] text-sre-text-muted">{errorPropagation.length}</span>
        </div>
        {errorPropagation.length === 0 ? (
          <p className="p-4 text-xs text-sre-text-muted">No propagation edges detected.</p>
        ) : (
          <div className="p-3 space-y-2">
            {errorPropagation.slice(0, 40).map((entry, index) => (
              <div key={`${entry.source_service}-${index}`} className="rounded-lg border border-sre-border/50 bg-sre-surface/25 p-2">
                <p className="text-xs font-semibold text-sre-text">{entry.source_service || 'unknown source'}</p>
                <p className="text-xs text-sre-text-muted mt-1">
                  Impacted: {(entry.affected_services || []).join(', ') || 'none'}
                </p>
                <p className={`text-xs mt-1 ${severityClass(entry.severity)}`}>
                  error_rate={Number(entry.error_rate || 0).toFixed(4)} severity={entry.severity || 'unknown'}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )

  if (compact) {
    return <div>{inner}</div>
  }

  return <Section>{inner}</Section>
}

RcaAnomalyPanels.propTypes = {
  report: PropTypes.object,
  compact: PropTypes.bool,
}
