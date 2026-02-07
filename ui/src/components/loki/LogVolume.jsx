import { Sparkline, Card } from '../../components/ui'

export default function LogVolume({ volume }) {
  if (!volume || !volume.length) return null

  const total = volume.reduce((a,b)=>a+b,0)
  const avg = Math.round(total / volume.length)
  const peak = Math.max(...volume)

  return (
    <Card title="Log Volume" subtitle="Over time">
      <div className="mb-3 w-full overflow-hidden">
        <Sparkline data={volume} width={280} height={100} stroke="#60a5fa" strokeWidth={2} fill="rgba(96, 165, 250, 0.2)" />
      </div>
      <div className="grid grid-cols-3 gap-3 text-xs">
        <div className="bg-sre-surface border border-sre-border rounded-lg p-2">
          <div className="text-sre-text-muted mb-1">Total</div>
          <div className="text-base font-bold text-sre-text">{total.toLocaleString()}</div>
        </div>
        <div className="bg-sre-surface border border-sre-border rounded-lg p-2">
          <div className="text-sre-text-muted mb-1">Avg/min</div>
          <div className="text-base font-bold text-sre-text">{avg.toLocaleString()}</div>
        </div>
        <div className="bg-sre-surface border border-sre-border rounded-lg p-2">
          <div className="text-sre-text-muted mb-1">Peak</div>
          <div className="text-base font-bold text-sre-text">{peak.toLocaleString()}</div>
        </div>
      </div>
    </Card>
  )
}
