import { Select } from '../ui'
import AlertItem from './AlertItem'
import HelpTooltip from '../HelpTooltip'
import { ALERT_SEVERITY_OPTIONS } from '../../utils/constants'

const AlertsTab = ({ filteredAlerts, filterSeverity, onFilterChange }) => {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="material-icons text-2xl text-sre-primary">warning</span>
          <div>
            <h2 className="text-xl font-semibold text-sre-text">Active Alerts</h2>
            <p className="text-sm text-sre-text-muted">
              {filteredAlerts.length > 0
                ? `You've got ${filteredAlerts.length} alert${filteredAlerts.length !== 1 ? 's' : ''} firing`
                : 'No active alerts'
              }
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Select aria-label="Filter alerts by severity" value={filterSeverity} onChange={(e) => onFilterChange(e.target.value)}>
            {ALERT_SEVERITY_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </Select>
          <HelpTooltip text="Filter alerts by severity level. Choose 'All' to see all alerts, or select specific severity to focus on critical or warning alerts." />
        </div>
      </div>

      {filteredAlerts.length > 0 ? (
        <div className="space-y-4">
          {filteredAlerts.map((alert) => {
            const alertKey = alert.fingerprint ?? alert.id ?? alert.starts_at ?? `${alert.labels?.alertname ?? 'alert'}-${alert.annotations?.summary ?? ''}-${alert.starts_at ?? alert.startsAt ?? ''}`
            return <AlertItem key={alertKey} alert={alert} />
          })}
        </div>
      ) : (
        <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
          <span className="material-icons text-5xl text-sre-text-muted mb-4 block">check_circle</span>
          <h3 className="text-xl font-semibold text-sre-text mb-2">No Active Alerts</h3>
          <p className="text-sre-text-muted mb-6 max-w-md mx-auto">
            All systems are running smoothly. No alerts are currently firing.
          </p>
        </div>
      )}
    </div>
  )
}

export default AlertsTab