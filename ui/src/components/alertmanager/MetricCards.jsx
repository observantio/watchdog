import { Card } from '../ui'
import { METRIC_DATA } from '../../utils/alertManagerConstants'

const MetricCards = ({ metricOrder, stats, onDragStart, onDragOver, onDrop, onDragEnd }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6 justify-center max-w-4xl mx-auto">
      {metricOrder.map((key) => {
        const data = METRIC_DATA[key]
        if (!data) return null // Skip invalid keys
        let value, detail

        switch (key) {
          case 'activeAlerts':
            value = stats.totalAlerts
            detail = <><span className="text-red-500 dark:text-red-400">{stats.critical} critical</span> · <span className="text-yellow-500 dark:text-yellow-400">{stats.warning} warning</span></>
            break
          case 'alertRules':
            value = `${stats.enabledRules}/${stats.totalRules}`
            detail = 'enabled'
            break
          case 'silences':
            value = stats.activeSilences
            detail = 'muting alerts'
            break
          default:
            value = 0
            detail = ''
        }

        return (
          <div
            key={key}
            draggable
            onDragStart={(e) => onDragStart(e, key)}
            onDragOver={onDragOver}
            onDrop={(e) => onDrop(e, key)}
            onDragEnd={onDragEnd}
            title="Drag to rearrange"
            className="cursor-move transition-transform duration-200 ease-out will-change-transform"
          >
            <Card className="p-4 relative overflow-visible bg-gradient-to-br from-sre-surface to-sre-surface/80 border-2 border-sre-border/50 hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm">
              <div className="absolute top-2 right-2 text-sre-text-muted hover:text-sre-text transition-colors">
                <span className="material-icons text-sm drag-handle" aria-hidden>drag_indicator</span>
              </div>
              <div className="text-sre-text-muted text-xs mb-1">{data.label}</div>
              <div className="text-2xl font-bold text-sre-text">{value}</div>
              <div className="text-xs text-sre-text-muted mt-1">{detail}</div>
            </Card>
          </div>
        )
      })}
    </div>
  )
}

export default MetricCards