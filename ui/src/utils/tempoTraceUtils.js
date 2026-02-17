`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { getServiceName, hasSpanError } from './helpers'

export function discoverServices(traces) {
  const discovered = new Set()
  traces.forEach((trace) => {
    (trace.spans || []).forEach((span) => {
      const name = getServiceName(span)
      if (name && name !== 'unknown') discovered.add(name)
    })
  })
  return Array.from(discovered).sort((a, b) => a.localeCompare(b))
}

export function computeTraceStats(filteredTraces) {
  if (!filteredTraces.length) return null

  const durations = filteredTraces.map((trace) => {
    if (!trace.spans?.length) return 0
    const rootSpan = trace.spans.find((span) => !span.parentSpanId && !span.parentSpanID) || trace.spans[0]
    return rootSpan?.duration || 0
  })

  const errorCount = filteredTraces.filter((trace) => trace.spans?.some(hasSpanError)).length
  const validDurations = durations.filter((duration) => duration > 0)
  const avgDuration = validDurations.length
    ? validDurations.reduce((acc, duration) => acc + duration, 0) / validDurations.length
    : 0
  const maxDuration = validDurations.length ? Math.max(...validDurations) : 0
  const minDuration = validDurations.length ? Math.min(...validDurations) : 0
  const errorRate = filteredTraces.length ? (errorCount / filteredTraces.length) * 100 : 0

  return {
    total: filteredTraces.length,
    avgDuration,
    maxDuration,
    minDuration,
    errorRate,
    errorCount,
  }
}
