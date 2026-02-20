`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { Sparkline, Card } from '../../components/ui'

export default function TraceVolume({ volume }) {
  if (!volume || !volume.length) return null


  const nums = volume
    .map((v) => {
      if (Array.isArray(v) && v.length > 1) return Number(v[1])
      return Number(v)
    })
    .map((n) => (Number.isNaN(n) ? 0 : n))

  const total = nums.reduce((a, b) => a + b, 0)
  const avg = nums.length ? Math.round(total / nums.length) : 0
  const peak = nums.length ? Math.max(...nums) : 0

  return (
    <Card title="Trace Volume" subtitle="Over time">
      <div className="mb-3 w-full overflow-hidden">
        <Sparkline data={nums} width={280} height={100} stroke="#34d399" strokeWidth={2} fill="rgba(52, 211, 153, 0.12)" />
      </div>
      <div className="grid grid-cols-3 gap-3 text-xs">
        <div className="bg-sre-surface border border-sre-border rounded-lg p-2 max-w-full">
          <div className="text-sre-text-muted mb-1">Total</div>
          <div className="text-base font-bold text-sre-text truncate">{total.toLocaleString()}</div>
        </div>
        <div className="bg-sre-surface border border-sre-border rounded-lg p-2 max-w-full">
          <div className="text-sre-text-muted mb-1">Avg/min</div>
          <div className="text-base font-bold text-sre-text truncate">{avg.toLocaleString()}</div>
        </div>
        <div className="bg-sre-surface border border-sre-border rounded-lg p-2 max-w-full">
          <div className="text-sre-text-muted mb-1">Peak</div>
          <div className="text-base font-bold text-sre-text truncate">{peak.toLocaleString()}</div>
        </div>
      </div>
    </Card>
  )
}
