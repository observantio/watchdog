import { useState } from 'react'
import PropTypes from 'prop-types'
import { MetricCard } from '../ui'

export function MetricsGrid({ metrics, metricOrder, onMetricOrderChange }) {
  const [draggedIndex, setDraggedIndex] = useState(null)

  const handleDragStart = (e, index) => {
    setDraggedIndex(index)
    e.dataTransfer.effectAllowed = 'move'
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }

  const handleDrop = (e, dropIndex) => {
    e.preventDefault()
    if (draggedIndex === null || draggedIndex === dropIndex) return

    const newOrder = [...metricOrder]
    const draggedItem = newOrder[draggedIndex]
    newOrder.splice(draggedIndex, 1)
    newOrder.splice(dropIndex, 0, draggedItem)

    // MetricsGrid is a presentational component; persist changes in the parent
    onMetricOrderChange(newOrder)
    setDraggedIndex(null)
  }

  const handleDragEnd = () => {
    setDraggedIndex(null)
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      {metricOrder.map((metricIndex, displayIndex) => {
        const metric = metrics[metricIndex]
        if (!metric) return null
        return (
          <button
            key={metric.id}
            draggable
            onDragStart={(e) => handleDragStart(e, displayIndex)}
            onDragOver={handleDragOver}
            onDrop={(e) => handleDrop(e, displayIndex)}
            onDragEnd={handleDragEnd}
            className={`cursor-move transition-transform duration-200 ease-out will-change-transform hover:shadow-lg relative ${
              draggedIndex === displayIndex ? 'opacity-50 scale-95 shadow-xl' : ''
            }`}
            title="Drag to rearrange"
            type="button"
          >
            <div className="absolute top-2 right-2 text-sre-text-muted hover:text-sre-text transition-colors z-10">
              <span className="material-icons text-sm drag-handle" aria-hidden>drag_indicator</span>
            </div>
            <MetricCard
              label={metric.label}
              value={metric.value}
              trend={metric.trend}
              status={metric.status}
              icon={metric.icon}
            />
          </button>
        )
      })}
    </div>
  )
}

MetricsGrid.propTypes = {
  metrics: PropTypes.array.isRequired,
  metricOrder: PropTypes.array.isRequired,
  onMetricOrderChange: PropTypes.func.isRequired,
}
