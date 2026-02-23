import PropTypes from 'prop-types'
import { Card } from '../ui'

function fmt(value, digits = 2) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '-'
  return num.toLocaleString(undefined, { maximumFractionDigits: digits })
}

function statusClass(value) {
  if (value === 'critical' || value === 'high') return 'text-red-300'
  if (value === 'medium' || value === 'warning') return 'text-amber-300'
  return 'text-emerald-300'
}

function TableSection({ title, columns, rows, rowKey, renderRow, emptyText }) {
  return (
    <div className="border border-sre-border rounded-xl bg-sre-surface/20 overflow-hidden">
      <div className="px-3 py-2 border-b border-sre-border bg-sre-surface/40">
        <h4 className="text-sm font-semibold text-sre-text">{title}</h4>
      </div>
      {rows.length === 0 ? (
        <p className="p-4 text-xs text-sre-text-muted">{emptyText}</p>
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

TableSection.propTypes = {
  title: PropTypes.string.isRequired,
  columns: PropTypes.arrayOf(PropTypes.string).isRequired,
  rows: PropTypes.array.isRequired,
  rowKey: PropTypes.func.isRequired,
  renderRow: PropTypes.func.isRequired,
  emptyText: PropTypes.string.isRequired,
}

export default function RcaForecastSloPanel({ report, forecast, slo }) {
  const reportForecasts = report?.forecasts || []
  const degradationSignals = report?.degradation_signals || []
  const forecastResults = forecast?.results || []
  const burnAlerts = slo?.burn_alerts || []
  const budgetStatus = slo?.budget_status || null

  return (
    <Card className="border border-sre-border p-4">
      <h3 className="text-lg text-sre-text font-semibold mb-3">Forecast and SLO</h3>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <TableSection
          title={`Forecast Signals (${reportForecasts.length})`}
          columns={['Metric', 'Severity', 'Details']}
          rows={reportForecasts}
          rowKey={(row, index) => `${row.metric_name || row.metric}-${index}`}
          emptyText="No forecast threshold breaches predicted."
          renderRow={(row) => (
            <>
              <td className="px-3 py-2 text-sre-text">{row.metric_name || row.metric || '-'}</td>
              <td className={`px-3 py-2 uppercase ${statusClass(row.severity)}`}>{row.severity || '-'}</td>
              <td className="px-3 py-2 text-sre-text-muted">{row.description || row.reason || '-'}</td>
            </>
          )}
        />

        <TableSection
          title={`Trajectory Output (${forecastResults.length})`}
          columns={['Metric', 'Forecast', 'Degradation']}
          rows={forecastResults}
          rowKey={(row, index) => `${row.metric}-${index}`}
          emptyText="No trajectory output returned."
          renderRow={(row) => (
            <>
              <td className="px-3 py-2 text-sre-text">{row.metric || '-'}</td>
              <td className={`px-3 py-2 ${row.forecast ? 'text-amber-300' : 'text-emerald-300'}`}>{row.forecast ? 'forecasted' : 'stable'}</td>
              <td className={`px-3 py-2 ${row.degradation ? 'text-red-300' : 'text-emerald-300'}`}>{row.degradation ? 'degrading' : 'healthy'}</td>
            </>
          )}
        />

        <TableSection
          title={`SLO Burn Alerts (${burnAlerts.length})`}
          columns={['Service', 'Window', 'Burn Rate', 'Severity']}
          rows={burnAlerts}
          rowKey={(row, index) => `${row.service}-${row.window_label}-${index}`}
          emptyText="No SLO burn alerts returned."
          renderRow={(row) => (
            <>
              <td className="px-3 py-2 text-sre-text">{row.service || '-'}</td>
              <td className="px-3 py-2 text-sre-text-muted">{row.window_label || '-'}</td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">{fmt(row.burn_rate)}</td>
              <td className={`px-3 py-2 uppercase ${statusClass(row.severity)}`}>{row.severity || '-'}</td>
            </>
          )}
        />

        <div className="border border-sre-border rounded-xl bg-sre-surface/20 p-3">
          <h4 className="text-sm font-semibold text-sre-text mb-2">Budget and Degradation</h4>
          {budgetStatus ? (
            <div className="space-y-2">
              <p className="text-xs text-sre-text-muted">
                Service: <span className="text-sre-text">{budgetStatus.service || '-'}</span>
              </p>
              <p className="text-xs text-sre-text-muted">
                Target availability: <span className="text-sre-text font-mono">{fmt(budgetStatus.target_availability, 4)}</span>
              </p>
              <p className="text-xs text-sre-text-muted">
                Current availability: <span className="text-sre-text font-mono">{fmt(budgetStatus.current_availability, 4)}</span>
              </p>
              <p className="text-xs text-sre-text-muted">
                Budget used: <span className="text-sre-text font-mono">{fmt(budgetStatus.budget_used_pct)}%</span>
              </p>
              <p className="text-xs text-sre-text-muted">
                Remaining minutes: <span className="text-sre-text font-mono">{fmt(budgetStatus.remaining_minutes, 1)}</span>
              </p>
            </div>
          ) : (
            <p className="text-xs text-sre-text-muted">No budget status returned.</p>
          )}
          <div className="mt-3">
            <p className="text-xs text-sre-text-muted mb-1">Degradation Signals</p>
            {degradationSignals.length === 0 ? (
              <p className="text-xs text-sre-text-muted">No degradation signals detected.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {degradationSignals.slice(0, 20).map((signal, index) => (
                  <span key={`${signal?.metric_name || signal?.metric || 'signal'}-${index}`} className="text-xs px-2 py-1 rounded-md border border-sre-border bg-sre-surface">
                    {signal?.metric_name || signal?.metric || 'signal'}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  )
}

RcaForecastSloPanel.propTypes = {
  report: PropTypes.object,
  forecast: PropTypes.object,
  slo: PropTypes.object,
}
