import PropTypes from 'prop-types'
import { Card } from '../ui'

export default function StatsCards({ stats }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <Card className="p-4">
        <div className="text-sre-text-muted text-xs mb-1">Active Alerts</div>
        <div className="text-2xl font-bold text-sre-text">{stats.totalAlerts}</div>
        <div className="text-xs text-sre-text-muted mt-1"><span className="text-red-500">{stats.critical} critical</span> · <span className="text-yellow-500">{stats.warning} warning</span></div>
      </Card>
      <Card className="p-4">
        <div className="text-sre-text-muted text-xs mb-1">Alert Rules</div>
        <div className="text-2xl font-bold text-sre-text">{stats.enabledRules}/{stats.totalRules}</div>
        <div className="text-xs text-sre-text-muted mt-1">enabled</div>
      </Card>
      <Card className="p-4">
        <div className="text-sre-text-muted text-xs mb-1">Notification Channels</div>
        <div className="text-2xl font-bold text-sre-text">{stats.enabledChannels}/{stats.totalChannels}</div>
        <div className="text-xs text-sre-text-muted mt-1">active</div>
      </Card>
      <Card className="p-4">
        <div className="text-sre-text-muted text-xs mb-1">Active Silences</div>
        <div className="text-2xl font-bold text-sre-text">{stats.activeSilences}</div>
        <div className="text-xs text-sre-text-muted mt-1">muting alerts</div>
      </Card>
    </div>
  )
}

StatsCards.propTypes = {
  stats: PropTypes.shape({
    totalAlerts: PropTypes.number,
    critical: PropTypes.number,
    warning: PropTypes.number,
    activeSilences: PropTypes.number,
    enabledRules: PropTypes.number,
    totalRules: PropTypes.number,
    enabledChannels: PropTypes.number,
    totalChannels: PropTypes.number,
  }).isRequired,
}
