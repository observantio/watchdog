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
  const timestamps = volume
    .map((v) => (Array.isArray(v) && v.length > 0 ? Number(v[0]) : NaN))
    .filter((t) => Number.isFinite(t))
  const firstTs = timestamps.length > 0 ? timestamps[0] : null
  const lastTs = timestamps.length > 1 ? timestamps[timestamps.length - 1] : null
  const rangeMinutes = firstTs !== null && lastTs !== null && lastTs > firstTs
    ? (lastTs - firstTs) / 60
    : nums.length
  const avg = rangeMinutes > 0 ? Math.round(total / rangeMinutes) : 0
  const peak = nums.length ? Math.max(...nums) : 0
  const firstValue = nums.length ? nums[0] : 0
  const lastValue = nums.length ? nums[nums.length - 1] : 0
  const trendLabel =
    lastValue > firstValue ? 'Rising' : lastValue < firstValue ? 'Falling' : 'Stable'

  return (
    <Card title="Trace Volume" subtitle={`Over time (${trendLabel})`}>
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
