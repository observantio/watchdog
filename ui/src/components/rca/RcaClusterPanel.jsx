import { useEffect, useMemo, useState } from 'react'
import PropTypes from 'prop-types'
import { Card } from '../ui'

function formatNumber(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '-'
  if (Math.abs(numeric) >= 1_000_000) return numeric.toExponential(2)
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 2 })
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

export default function RcaClusterPanel({ report }) {
  const clusters = report?.anomaly_clusters || []
  const points = useMemo(() => buildClusterPoints(clusters), [clusters])
  const [selectedPointId, setSelectedPointId] = useState(points[0]?.id || null)

  useEffect(() => {
    if (points.length === 0) {
      setSelectedPointId(null)
      return
    }
    const currentExists = points.some((point) => point.id === selectedPointId)
    if (!currentExists) {
      setSelectedPointId(points[0].id)
    }
  }, [points, selectedPointId])

  const selectedPoint = points.find((point) => point.id === selectedPointId) || null

  const chart = useMemo(() => {
    if (points.length === 0) {
      return {
        svgPoints: [],
        bounds: null,
      }
    }
    const xMin = Math.min(...points.map((point) => point.ts))
    const xMax = Math.max(...points.map((point) => point.ts))
    const yMin = Math.min(...points.map((point) => point.value))
    const yMax = Math.max(...points.map((point) => point.value))
    const maxSize = Math.max(...points.map((point) => point.size), 1)

    const width = 780
    const height = 280
    const padLeft = 40
    const padRight = 18
    const padTop = 18
    const padBottom = 32
    const plotWidth = width - padLeft - padRight
    const plotHeight = height - padTop - padBottom
    const xSpan = Math.max(1, xMax - xMin)
    const ySpan = Math.max(1, yMax - yMin)

    const projectX = (value) => padLeft + ((value - xMin) / xSpan) * plotWidth
    const projectY = (value) => padTop + (1 - (value - yMin) / ySpan) * plotHeight
    const radius = (size) => 6 + (Math.max(0, size) / maxSize) * 22

    return {
      bounds: { xMin, xMax, yMin, yMax },
      width,
      height,
      svgPoints: points.map((point) => ({
        ...point,
        cx: projectX(point.ts),
        cy: projectY(point.value),
        r: radius(point.size),
      })),
      gridLines: [0.25, 0.5, 0.75].map((ratio) => padTop + plotHeight * ratio),
      labels: {
        left: `${formatNumber(yMin)}`,
        center: `${formatNumber((yMin + yMax) / 2)}`,
        right: `${formatNumber(yMax)}`,
        start: `${formatNumber(xMin)}`,
        end: `${formatNumber(xMax)}`,
      },
    }
  }, [points])

  return (
    <Card className="border border-sre-border p-4">
      <h3 className="text-lg text-sre-text font-semibold mb-3">Anomaly Clusters</h3>
      {clusters.length === 0 ? (
        <p className="text-sm text-sre-text-muted">No clusters were produced for this report window.</p>
      ) : (
        <div className="space-y-3">
          <div className="border border-sre-border rounded-xl p-3 bg-sre-surface/20">
            <p className="text-xs text-sre-text-muted mb-2">
              Bubble size = anomaly count, X = centroid timestamp, Y = centroid value
            </p>
            <div className="overflow-x-auto">
              <svg
                viewBox={`0 0 ${chart.width} ${chart.height}`}
                className="w-full min-w-[740px] h-[280px]"
                role="img"
                aria-label="Anomaly cluster bubble chart"
              >
                <rect x="0" y="0" width={chart.width} height={chart.height} fill="transparent" />
                {chart.gridLines?.map((lineY) => (
                  <line
                    key={`grid-${lineY}`}
                    x1="40"
                    y1={lineY}
                    x2={chart.width - 18}
                    y2={lineY}
                    stroke="rgba(148, 163, 184, 0.22)"
                    strokeDasharray="4 4"
                  />
                ))}
                {chart.svgPoints?.map((point) => {
                  const selected = point.id === selectedPointId
                  return (
                    <g
                      key={point.id}
                      onClick={() => setSelectedPointId(point.id)}
                      className="cursor-pointer"
                    >
                      <circle
                        cx={point.cx}
                        cy={point.cy}
                        r={point.r}
                        fill={selected ? 'rgba(59, 130, 246, 0.55)' : 'rgba(56, 189, 248, 0.35)'}
                        stroke={selected ? 'rgb(125, 211, 252)' : 'rgba(56, 189, 248, 0.8)'}
                        strokeWidth={selected ? 2 : 1}
                      />
                      <text
                        x={point.cx}
                        y={point.cy}
                        textAnchor="middle"
                        dominantBaseline="central"
                        className="fill-sre-text text-[11px] font-semibold"
                      >
                        {point.clusterId}
                      </text>
                    </g>
                  )
                })}
                <text x="12" y="24" className="fill-sre-text-muted text-[11px]">{chart.labels?.right}</text>
                <text x="12" y="145" className="fill-sre-text-muted text-[11px]">{chart.labels?.center}</text>
                <text x="12" y="260" className="fill-sre-text-muted text-[11px]">{chart.labels?.left}</text>
                <text x="40" y="275" className="fill-sre-text-muted text-[11px]">{chart.labels?.start}</text>
                <text x={chart.width - 120} y="275" className="fill-sre-text-muted text-[11px]">{chart.labels?.end}</text>
              </svg>
            </div>
          </div>

          {selectedPoint && (
            <div className="border border-sre-border rounded-xl p-3 bg-sre-surface/30">
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <p className="text-sm font-semibold text-sre-text">Cluster {selectedPoint.clusterId}</p>
                <span className="text-xs px-2 py-0.5 rounded-full bg-sre-primary/15 text-sre-primary border border-sre-primary/30">
                  {selectedPoint.size} anomalies
                </span>
              </div>
              <p className="text-xs text-sre-text-muted">
                Centroid timestamp: {formatNumber(selectedPoint.ts)} | Centroid value: {formatNumber(selectedPoint.value)}
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {selectedPoint.metrics.slice(0, 24).map((metric) => (
                  <span key={metric} className="text-xs px-2 py-1 rounded-md bg-sre-surface border border-sre-border text-sre-text">
                    {metric}
                  </span>
                ))}
                {selectedPoint.metrics.length > 24 && (
                  <span className="text-xs px-2 py-1 rounded-md bg-sre-surface border border-sre-border text-sre-text-muted">
                    +{selectedPoint.metrics.length - 24} more
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

RcaClusterPanel.propTypes = {
  report: PropTypes.object,
}
