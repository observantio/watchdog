`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { Card } from '../ui'
import { formatDuration } from '../../utils/formatters'

export default function TempoStats({ traceStats }) {
  if (!traceStats) return null

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
      {[
        { label: 'Total Traces', value: traceStats.total, color: 'text-sre-text' },
        { label: 'Avg Duration', value: formatDuration(traceStats.avgDuration), color: 'text-sre-text' },
        { label: 'Max Duration', value: formatDuration(traceStats.maxDuration), color: 'text-sre-text' },
        { label: 'Error Rate', value: `${traceStats.errorRate.toFixed(1)}%`, color: traceStats.errorRate > 5 ? 'text-red-500' : 'text-green-500' },
        { label: 'Errors', value: traceStats.errorCount, color: traceStats.errorCount > 0 ? 'text-red-500' : 'text-green-500' },
      ].map(stat => (
        <Card key={stat.label} className="p-4 relative overflow-visible bg-gradient-to-br from-sre-surface to-sre-surface/80 border-2 border-sre-border/50 hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm">
          <div className="text-sre-text-muted text-xs mb-1">{stat.label}</div>
          <div className={`text-2xl font-bold ${stat.color}`}>{stat.value}</div>
        </Card>
      ))}
    </div>
  )
}