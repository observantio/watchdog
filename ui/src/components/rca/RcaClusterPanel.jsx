import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import PropTypes from 'prop-types'
import Section from './Section'

function formatNumber(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '-'
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function formatTimestamp(ts) {
  const n = Number(ts)
  if (!Number.isFinite(n) || n === 0) return '-'
  const date = new Date(n > 1e12 ? n : n * 1000)
  return date.toLocaleString()
}

function buildClusterPoints(clusters) {
  return (clusters || []).map((cluster, index) => ({
    id: `${cluster.cluster_id}-${index}`,
    clusterId: cluster.cluster_id,
    size: Number(cluster.size || 0),
    ts: Number(cluster.centroid_timestamp || 0),
    value: Number(cluster.centroid_value || 0),
    metrics: Array.isArray(cluster.metric_names) ? cluster.metric_names : [],
  }))
}

const SORT_OPTIONS = [
  { label: 'Size ↓', value: 'size_desc' },
  { label: 'Size ↑', value: 'size_asc' },
  { label: 'Time ↓', value: 'ts_desc' },
  { label: 'Time ↑', value: 'ts_asc' },
  { label: 'Value ↓', value: 'value_desc' },
]

function ClusterListItem({ point, selected, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 rounded-lg border transition-all duration-150 group ${
        selected
          ? 'border-blue-400/60 bg-blue-500/15 shadow-[0_0_12px_rgba(59,130,246,0.2)]'
          : 'border-sre-border bg-sre-surface/30 hover:border-blue-400/30 hover:bg-sre-surface/50'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition-colors ${
              selected ? 'bg-blue-500 text-white' : 'bg-sre-surface border border-sre-border text-sre-text-muted group-hover:border-blue-400/40'
            }`}
          >
            {point.clusterId}
          </span>
          <span className="text-xs text-sre-text-muted truncate">{formatTimestamp(point.ts)}</span>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span className="text-[10px] text-sre-text-muted">{point.metrics.length} metrics</span>
          <span
            className={`text-xs px-1.5 py-0.5 rounded font-medium ${
              selected ? 'bg-blue-500/25 text-blue-300' : 'bg-sre-surface text-sre-text-muted'
            }`}
          >
            {formatNumber(point.size)}
          </span>
        </div>
      </div>
      <div className={`mt-1 h-1 rounded-full overflow-hidden bg-sre-surface`}>
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{
            width: `${Math.min(100, (point.size / Math.max(point.size, 1)) * 100)}%`,
            background: selected ? 'rgb(59,130,246)' : 'rgba(56,189,248,0.5)',
          }}
        />
      </div>
    </button>
  )
}

function MiniSparkBar({ value, max, color = 'rgba(56,189,248,0.7)' }) {
  const pct = max > 0 ? Math.min(1, value / max) : 0
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex-1 h-1.5 rounded-full bg-sre-surface overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct * 100}%`, background: color }} />
      </div>
      <span className="text-[10px] text-sre-text-muted w-10 text-right tabular-nums">{formatNumber(value)}</span>
    </div>
  )
}

export default function RcaClusterPanel({ report, compact = false }) {
  const clusters = report?.anomaly_clusters || []
  const points = useMemo(() => buildClusterPoints(clusters), [clusters])
  const [selectedPointId, setSelectedPointId] = useState(points[0]?.id || null)
  const [sortBy, setSortBy] = useState('size_desc')
  const [searchTerm, setSearchTerm] = useState('')
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState(null)
  const [hoveredPointId, setHoveredPointId] = useState(null)
  const [tooltip, setTooltip] = useState(null)
  const [metricSearch, setMetricSearch] = useState('')
  const containerRef = useRef(null)
  const svgRef = useRef(null)

  useEffect(() => {
    if (points.length === 0) { setSelectedPointId(null); return }
    if (!points.some((p) => p.id === selectedPointId)) setSelectedPointId(points[0].id)
  }, [points, selectedPointId])

  const selectedPoint = points.find((p) => p.id === selectedPointId) || null

  const sortedPoints = useMemo(() => {
    const sorted = [...points]
    switch (sortBy) {
      case 'size_desc': return sorted.sort((a, b) => b.size - a.size)
      case 'size_asc': return sorted.sort((a, b) => a.size - b.size)
      case 'ts_desc': return sorted.sort((a, b) => b.ts - a.ts)
      case 'ts_asc': return sorted.sort((a, b) => a.ts - b.ts)
      case 'value_desc': return sorted.sort((a, b) => b.value - a.value)
      default: return sorted
    }
  }, [points, sortBy])

  const filteredPoints = useMemo(() => {
    if (!searchTerm.trim()) return sortedPoints
    const q = searchTerm.toLowerCase()
    return sortedPoints.filter(
      (p) =>
        String(p.clusterId).includes(q) ||
        p.metrics.some((m) => m.toLowerCase().includes(q))
    )
  }, [sortedPoints, searchTerm])

  const maxSize = useMemo(() => Math.max(...points.map((p) => p.size), 1), [points])

  const chart = useMemo(() => {
    if (points.length === 0) return { svgPoints: [], bounds: null }

    const xMin = Math.min(...points.map((p) => p.ts))
    const xMax = Math.max(...points.map((p) => p.ts))
    const yMin = Math.min(...points.map((p) => p.value))
    const yMax = Math.max(...points.map((p) => p.value))

    const width = 820
    const height = 300
    const padLeft = 50
    const padRight = 20
    const padTop = 20
    const padBottom = 36
    const plotWidth = width - padLeft - padRight
    const plotHeight = height - padTop - padBottom
    const xSpan = Math.max(1, xMax - xMin)
    const ySpan = Math.max(1, yMax - yMin)

    const projectX = (v) => padLeft + ((v - xMin) / xSpan) * plotWidth
    const projectY = (v) => padTop + (1 - (v - yMin) / ySpan) * plotHeight
    const radius = (size) => 7 + (Math.max(0, size) / maxSize) * 24

    const ySteps = 5
    const yGridLines = Array.from({ length: ySteps }, (_, i) => {
      const ratio = i / (ySteps - 1)
      return {
        y: padTop + plotHeight * ratio,
        label: formatNumber(yMax - ratio * (yMax - yMin)),
      }
    })

    const xSteps = 4
    const xGridLines = Array.from({ length: xSteps }, (_, i) => {
      const ratio = i / (xSteps - 1)
      return {
        x: padLeft + plotWidth * ratio,
        label: formatTimestamp(xMin + ratio * xSpan),
      }
    })

    return {
      bounds: { xMin, xMax, yMin, yMax },
      width,
      height,
      padLeft,
      padBottom,
      plotWidth,
      plotHeight,
      svgPoints: points.map((p) => ({
        ...p,
        cx: projectX(p.ts),
        cy: projectY(p.value),
        r: radius(p.size),
      })),
      yGridLines,
      xGridLines,
    }
  }, [points, maxSize])

  const handleWheel = useCallback((e) => {
    e.preventDefault()
    const delta = e.deltaY > 0 ? 0.85 : 1.18
    setZoom((z) => Math.min(5, Math.max(0.5, z * delta)))
  }, [])

  const handleMouseDown = useCallback((e) => {
    if (e.button !== 0) return
    setIsDragging(true)
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y })
  }, [pan])

  const handleMouseMove = useCallback((e) => {
    if (!isDragging || !dragStart) return
    setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y })
  }, [isDragging, dragStart])

  const handleMouseUp = useCallback(() => {
    setIsDragging(false)
    setDragStart(null)
  }, [])

  const resetView = () => { setZoom(1); setPan({ x: 0, y: 0 }) }

  const stats = useMemo(() => ({
    total: points.length,
    totalAnomalies: points.reduce((s, p) => s + p.size, 0),
    avgSize: points.length ? points.reduce((s, p) => s + p.size, 0) / points.length : 0,
    largestCluster: points.reduce((best, p) => (!best || p.size > best.size ? p : best), null),
  }), [points])

  const filteredMetrics = useMemo(() => {
    if (!selectedPoint) return []
    if (!metricSearch.trim()) return selectedPoint.metrics
    return selectedPoint.metrics.filter((m) => m.toLowerCase().includes(metricSearch.toLowerCase()))
  }, [selectedPoint, metricSearch])

  const content = (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-sre-text tracking-tight">Anomaly Clusters</h3>
          {clusters.length > 0 && (
            <p className="text-xs text-sre-text-muted mt-0.5">
              {stats.total} clusters · {formatNumber(stats.totalAnomalies)} total anomalies
            </p>
          )}
        </div>
        {clusters.length > 0 && (
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 p-0.5 rounded-lg bg-sre-surface border border-sre-border">
              {SORT_OPTIONS.map((o) => (
                <button
                  key={o.value}
                  onClick={() => setSortBy(o.value)}
                  className={`text-[10px] px-2 py-1 rounded-md transition-all ${
                    sortBy === o.value
                      ? 'bg-blue-500/20 text-blue-300 border border-blue-400/30'
                      : 'text-sre-text-muted hover:text-sre-text'
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {clusters.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 rounded-xl border border-dashed border-sre-border bg-sre-surface/10">
          <svg className="w-8 h-8 text-sre-text-muted mb-2 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm text-sre-text-muted">No clusters were produced for this report window.</p>
        </div>
      ) : (
        <div className="grid grid-cols-[1fr_220px] gap-3" style={{ minHeight: 0 }}>
          <div className="flex flex-col gap-3 min-w-0">
            <div className="grid grid-cols-4 gap-2">
              {[
                { label: 'Clusters', value: stats.total },
                { label: 'Anomalies', value: formatNumber(stats.totalAnomalies) },
                { label: 'Avg Size', value: formatNumber(stats.avgSize) },
                { label: 'Largest', value: stats.largestCluster ? `#${stats.largestCluster.clusterId} (${formatNumber(stats.largestCluster.size)})` : '-' },
              ].map(({ label, value }) => (
                <div key={label} className="rounded-lg border border-sre-border bg-sre-surface/20 px-3 py-2">
                  <p className="text-[10px] text-sre-text-muted uppercase tracking-wider">{label}</p>
                  <p className="text-sm font-semibold text-sre-text mt-0.5 truncate">{value}</p>
                </div>
              ))}
            </div>

            <div className="relative rounded-xl border border-sre-border bg-sre-surface/10 overflow-hidden">
              <div className="absolute top-2 right-2 z-10 flex items-center gap-1">
                <span className="text-[9px] text-sre-text-muted mr-1">scroll to zoom · drag to pan</span>
                <button
                  onClick={() => setZoom((z) => Math.min(5, z * 1.2))}
                  className="w-6 h-6 flex items-center justify-center rounded border border-sre-border bg-sre-surface/80 text-sre-text-muted hover:text-sre-text text-xs"
                >+</button>
                <button
                  onClick={() => setZoom((z) => Math.max(0.5, z * 0.8))}
                  className="w-6 h-6 flex items-center justify-center rounded border border-sre-border bg-sre-surface/80 text-sre-text-muted hover:text-sre-text text-xs"
                >−</button>
                <button
                  onClick={resetView}
                  className="w-6 h-6 flex items-center justify-center rounded border border-sre-border bg-sre-surface/80 text-sre-text-muted hover:text-sre-text text-[9px]"
                  title="Reset view"
                >⊡</button>
              </div>

              <div
                className={`relative overflow-hidden ${isDragging ? 'cursor-grabbing' : 'cursor-grab'}`}
                ref={containerRef}
                style={{ height: 300 }}
                onWheel={handleWheel}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
              >
                <svg
                  ref={svgRef}
                  viewBox={`0 0 ${chart.width} ${chart.height}`}
                  className="w-full h-full"
                  style={{
                    transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
                    transformOrigin: 'center center',
                    transition: isDragging ? 'none' : 'transform 0.1s ease-out',
                  }}
                  role="img"
                  aria-label="Anomaly cluster bubble chart"
                >
                  <defs>
                    <radialGradient id="bubbleGrad" cx="40%" cy="35%" r="60%">
                      <stop offset="0%" stopColor="rgba(147,197,253,0.9)" />
                      <stop offset="100%" stopColor="rgba(59,130,246,0.3)" />
                    </radialGradient>
                    <radialGradient id="bubbleGradActive" cx="40%" cy="35%" r="60%">
                      <stop offset="0%" stopColor="rgba(167,243,208,0.9)" />
                      <stop offset="100%" stopColor="rgba(16,185,129,0.35)" />
                    </radialGradient>
                    <filter id="glow">
                      <feGaussianBlur stdDeviation="3" result="coloredBlur" />
                      <feMerge>
                        <feMergeNode in="coloredBlur" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                    <filter id="glowStrong">
                      <feGaussianBlur stdDeviation="5" result="coloredBlur" />
                      <feMerge>
                        <feMergeNode in="coloredBlur" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                  </defs>

                  <rect x="0" y="0" width={chart.width} height={chart.height} fill="transparent" />

                  {chart.yGridLines?.map(({ y, label }) => (
                    <g key={`yg-${y}`}>
                      <line x1={chart.padLeft} y1={y} x2={chart.width - 20} y2={y} stroke="rgba(148,163,184,0.12)" strokeDasharray="3 5" />
                      <text x={chart.padLeft - 6} y={y + 4} textAnchor="end" className="fill-sre-text-muted" style={{ fontSize: 9 }}>{label}</text>
                    </g>
                  ))}

                  {chart.xGridLines?.map(({ x, label }, i) => (
                    <g key={`xg-${x}`}>
                      <line x1={x} y1={chart.padTop ?? 20} x2={x} y2={(chart.height ?? 300) - (chart.padBottom ?? 36)} stroke="rgba(148,163,184,0.10)" strokeDasharray="3 5" />
                      {(i === 0 || i === chart.xGridLines.length - 1) && (
                        <text
                          x={x}
                          y={(chart.height ?? 300) - 8}
                          textAnchor={i === 0 ? 'start' : 'end'}
                          className="fill-sre-text-muted"
                          style={{ fontSize: 9 }}
                        >
                          {label}
                        </text>
                      )}
                    </g>
                  ))}

                  {chart.svgPoints?.map((point) => {
                    const selected = point.id === selectedPointId
                    const hovered = point.id === hoveredPointId
                    const isActive = selected || hovered
                    return (
                      <g
                        key={point.id}
                        onClick={(e) => { e.stopPropagation(); setSelectedPointId(point.id) }}
                        onMouseEnter={(e) => {
                          setHoveredPointId(point.id)
                          if (containerRef.current) {
                            const rect = containerRef.current.getBoundingClientRect()
                            setTooltip({ point, x: e.clientX - rect.left, y: e.clientY - rect.top - 12 })
                          }
                        }}
                        onMouseMove={(e) => {
                          if (containerRef.current) {
                            const rect = containerRef.current.getBoundingClientRect()
                            const x = Math.min(Math.max(0, e.clientX - rect.left), rect.width - 180)
                            const y = Math.min(Math.max(0, e.clientY - rect.top - 12), rect.height - 100)
                            setTooltip((t) => t ? { ...t, x, y } : null)
                          }
                        }}
                        onMouseLeave={() => { setHoveredPointId(null); setTooltip(null) }}
                        className="cursor-pointer"
                        style={{ filter: isActive ? 'url(#glowStrong)' : undefined }}
                      >
                        {selected && (
                          <circle
                            cx={point.cx}
                            cy={point.cy}
                            r={point.r + 6}
                            fill="none"
                            stroke="rgba(52,211,153,0.35)"
                            strokeWidth={2}
                            strokeDasharray="4 3"
                          >
                            <animateTransform
                              attributeName="transform"
                              type="rotate"
                              from={`0 ${point.cx} ${point.cy}`}
                              to={`360 ${point.cx} ${point.cy}`}
                              dur="8s"
                              repeatCount="indefinite"
                            />
                          </circle>
                        )}
                        <circle
                          cx={point.cx}
                          cy={point.cy}
                          r={point.r}
                          fill={isActive ? 'url(#bubbleGradActive)' : 'url(#bubbleGrad)'}
                          stroke={selected ? 'rgba(52,211,153,0.9)' : hovered ? 'rgba(147,197,253,0.9)' : 'rgba(96,165,250,0.5)'}
                          strokeWidth={selected ? 1.5 : 1}
                          opacity={isActive ? 1 : 0.75}
                        />
                        <text
                          x={point.cx}
                          y={point.cy - 1}
                          textAnchor="middle"
                          dominantBaseline="central"
                          style={{ fontSize: Math.max(9, Math.min(13, point.r * 0.7)), fontWeight: 700, fill: isActive ? 'rgb(6,78,59)' : 'rgb(30,58,138)', pointerEvents: 'none' }}
                        >
                          {point.clusterId}
                        </text>
                        {point.r > 18 && (
                          <text
                            x={point.cx}
                            y={point.cy + point.r * 0.38}
                            textAnchor="middle"
                            dominantBaseline="central"
                            style={{ fontSize: 8, fill: isActive ? 'rgb(6,95,70)' : 'rgb(37,99,235)', opacity: 0.85, pointerEvents: 'none' }}
                          >
                            {formatNumber(point.size)}
                          </text>
                        )}
                      </g>
                    )
                  })}
                </svg>

                {tooltip && (
                  <div
                    style={{ left: tooltip.x + 12, top: tooltip.y, maxWidth: 200, pointerEvents: 'none' }}
                    className="absolute z-30 rounded-lg border border-sre-border bg-sre-bg-card shadow-xl text-xs p-3 space-y-1"
                  >
                    <p className="font-semibold text-sre-text border-b border-sre-border pb-1 mb-1">
                      Cluster {tooltip.point.clusterId}
                    </p>
                    <div className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
                      <span className="text-sre-text-muted">Size</span>
                      <span className="text-sre-text font-medium">{formatNumber(tooltip.point.size)} anomalies</span>
                      <span className="text-sre-text-muted">Time</span>
                      <span className="text-sre-text">{formatTimestamp(tooltip.point.ts)}</span>
                      <span className="text-sre-text-muted">Value</span>
                      <span className="text-sre-text">{formatNumber(tooltip.point.value)}</span>
                      <span className="text-sre-text-muted">Metrics</span>
                      <span className="text-sre-text">{tooltip.point.metrics.length}</span>
                    </div>
                    {tooltip.point.metrics.length > 0 && (
                      <p className="text-sre-text-muted pt-1 truncate">{tooltip.point.metrics.slice(0, 3).join(', ')}{tooltip.point.metrics.length > 3 ? '…' : ''}</p>
                    )}
                  </div>
                )}
              </div>

              <div className="px-3 py-1.5 border-t border-sre-border/50 flex items-center gap-3">
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-3 rounded-full border border-blue-400/80" style={{ background: 'rgba(147,197,253,0.6)' }} />
                  <span className="text-[10px] text-sre-text-muted">default</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-3 rounded-full border border-emerald-400/80" style={{ background: 'rgba(167,243,208,0.7)' }} />
                  <span className="text-[10px] text-sre-text-muted">selected / hovered</span>
                </div>
                <div className="ml-auto text-[10px] text-sre-text-muted">bubble area ∝ anomaly count</div>
              </div>
            </div>

            {selectedPoint && (
              <div className="rounded-xl border border-sre-border bg-sre-surface/15 overflow-hidden">
                <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-sre-border/50">
                  <div className="flex items-center gap-2">
                    <span className="w-6 h-6 rounded-full bg-emerald-500/20 border border-emerald-400/40 text-emerald-300 text-xs font-bold flex items-center justify-center">
                      {selectedPoint.clusterId}
                    </span>
                    <p className="text-sm font-semibold text-sre-text">Cluster {selectedPoint.clusterId}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-400/30 font-medium">
                      {formatNumber(selectedPoint.size)} anomalies
                    </span>
                    <span className="text-xs px-2.5 py-0.5 rounded-full bg-sre-surface text-sre-text-muted border border-sre-border">
                      {selectedPoint.metrics.length} metrics
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-px bg-sre-border/30">
                  {[
                    { label: 'Centroid Time', value: formatTimestamp(selectedPoint.ts) },
                    { label: 'Centroid Value', value: formatNumber(selectedPoint.value) },
                  ].map(({ label, value }) => (
                    <div key={label} className="bg-sre-surface/10 px-4 py-2.5">
                      <p className="text-[10px] uppercase tracking-wider text-sre-text-muted">{label}</p>
                      <p className="text-sm text-sre-text font-medium mt-0.5 truncate">{value}</p>
                    </div>
                  ))}
                </div>

                <div className="px-4 py-3">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-medium text-sre-text-muted uppercase tracking-wider">Metrics</p>
                    {selectedPoint.metrics.length > 8 && (
                      <input
                        type="text"
                        placeholder="filter…"
                        value={metricSearch}
                        onChange={(e) => setMetricSearch(e.target.value)}
                        className="text-xs bg-sre-surface border border-sre-border rounded-md px-2 py-0.5 text-sre-text placeholder:text-sre-text-muted/50 outline-none focus:border-blue-400/40 w-28"
                      />
                    )}
                  </div>
                  <div className="flex flex-wrap gap-1.5 max-h-[96px] overflow-y-auto">
                    {filteredMetrics.slice(0, 40).map((metric) => (
                      <span
                        key={metric}
                        className="text-xs px-2 py-0.5 rounded-md bg-sre-surface border border-sre-border text-sre-text hover:border-blue-400/40 transition-colors cursor-default"
                      >
                        {metric}
                      </span>
                    ))}
                    {filteredMetrics.length > 40 && (
                      <span className="text-xs px-2 py-0.5 rounded-md bg-sre-surface border border-sre-border text-sre-text-muted">
                        +{filteredMetrics.length - 40} more
                      </span>
                    )}
                    {filteredMetrics.length === 0 && (
                      <p className="text-xs text-sre-text-muted">No metrics match.</p>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-2 min-w-0">
            <div className="relative">
              <input
                type="text"
                placeholder="Search clusters…"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full text-xs bg-sre-surface border border-sre-border rounded-lg px-3 py-1.5 pl-7 text-sre-text placeholder:text-sre-text-muted/50 outline-none focus:border-blue-400/40 transition-colors"
              />
              <svg className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-sre-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>

            <div className="flex flex-col gap-1.5 overflow-y-auto" style={{ maxHeight: 440 }}>
              {filteredPoints.map((point) => (
                <div key={point.id}>
                  <ClusterListItem
                    point={{ ...point, _maxSize: maxSize }}
                    selected={point.id === selectedPointId}
                    onClick={() => setSelectedPointId(point.id)}
                  />
                  <div className="px-1 mt-1">
                    <MiniSparkBar value={point.size} max={maxSize} color={point.id === selectedPointId ? 'rgb(52,211,153)' : 'rgba(56,189,248,0.6)'} />
                  </div>
                </div>
              ))}
              {filteredPoints.length === 0 && (
                <p className="text-xs text-sre-text-muted text-center py-4">No clusters match.</p>
              )}
            </div>

            {filteredPoints.length < points.length && (
              <p className="text-[10px] text-sre-text-muted text-center">
                {filteredPoints.length} of {points.length} shown
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )

  if (compact) return <div>{content}</div>
  return <Section>{content}</Section>
}

RcaClusterPanel.propTypes = {
  report: PropTypes.object,
  compact: PropTypes.bool,
}