import { useEffect, useMemo, useRef, useState } from "react";
import PropTypes from "prop-types";
import Section from "./Section";

function formatNumber(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatTimestamp(ts) {
  const n = Number(ts);
  if (!Number.isFinite(n) || n === 0) return "-";
  const date = new Date(n > 1e12 ? n : n * 1000);
  return date.toLocaleString();
}

function buildClusterPoints(clusters) {
  return (clusters || []).map((cluster, index) => ({
    id: `${cluster.cluster_id}-${index}`,
    clusterId: cluster.cluster_id,
    size: Number(cluster.size || 0),
    ts: Number(cluster.centroid_timestamp || 0),
    value: Number(cluster.centroid_value || 0),
    metrics: Array.isArray(cluster.metric_names) ? cluster.metric_names : [],
  }));
}

export default function RcaClusterPanel({ report, compact = false }) {
  const clusters = useMemo(
    () => report?.anomaly_clusters || [],
    [report?.anomaly_clusters],
  );
  const points = useMemo(() => buildClusterPoints(clusters), [clusters]);
  const [selectedPointId, setSelectedPointId] = useState(points[0]?.id || null);

  useEffect(() => {
    if (points.length === 0) {
      setSelectedPointId(null);
      return;
    }
    const currentExists = points.some((point) => point.id === selectedPointId);
    if (!currentExists) {
      setSelectedPointId(points[0].id);
    }
  }, [points, selectedPointId]);

  const selectedPoint =
    points.find((point) => point.id === selectedPointId) || null;

  const [hoveredPointId, setHoveredPointId] = useState(null);
  const [tooltip, setTooltip] = useState(null);
  const containerRef = useRef(null);

  const chart = useMemo(() => {
    if (points.length === 0) return { svgPoints: [], bounds: null };

    const xMin = Math.min(...points.map((p) => p.ts));
    const xMax = Math.max(...points.map((p) => p.ts));
    const yMin = Math.min(...points.map((p) => p.value));
    const yMax = Math.max(...points.map((p) => p.value));
    const maxSize = Math.max(...points.map((p) => p.size), 1);

    const width = 780;
    const height = 280;
    const padLeft = 40;
    const padRight = 18;
    const padTop = 18;
    const padBottom = 32;
    const plotWidth = width - padLeft - padRight;
    const plotHeight = height - padTop - padBottom;
    const xSpan = Math.max(1, xMax - xMin);
    const ySpan = Math.max(1, yMax - yMin);

    const projectX = (v) => padLeft + ((v - xMin) / xSpan) * plotWidth;
    const projectY = (v) => padTop + (1 - (v - yMin) / ySpan) * plotHeight;
    const radius = (size) => 6 + (Math.max(0, size) / maxSize) * 22;

    return {
      bounds: { xMin, xMax, yMin, yMax },
      width,
      height,
      svgPoints: points.map((p) => ({
        ...p,
        cx: projectX(p.ts),
        cy: projectY(p.value),
        r: radius(p.size),
      })),
      gridLines: [0.25, 0.5, 0.75].map((ratio) => padTop + plotHeight * ratio),
      labels: {
        left: formatNumber(yMin),
        center: formatNumber((yMin + yMax) / 2),
        right: formatNumber(yMax),
        start: formatTimestamp(xMin),
        end: formatTimestamp(xMax),
      },
    };
  }, [points]);

  const content = (
    <>
      <h3 className="text-lg text-sre-text font-semibold mb-3">
        Anomaly Clusters
      </h3>
      {clusters.length === 0 ? (
        <p className="text-sm text-sre-text-muted">
          No clusters were produced for this report window.
        </p>
      ) : (
        <div className="space-y-3">
          <div
            className={`${compact ? "" : "border border-sre-border rounded-xl"} bg-sre-surface/20`}
          >
            <p className="text-xs text-sre-text-muted mb-2">
              Each circle is a cluster. Size shows the number of anomalies,
              horizontal position is the centroid time and vertical position is
              centroid value.
            </p>
            <div className="relative my-5 overflow-hidden" ref={containerRef}>
              <svg
                viewBox={`0 0 ${chart.width} ${chart.height}`}
                className="w-full h-[280px]"
                role="img"
                aria-label="Anomaly cluster bubble chart"
              >
                <rect
                  x="0"
                  y="0"
                  width={chart.width}
                  height={chart.height}
                  fill="transparent"
                />
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
                  const selected = point.id === selectedPointId;
                  const hovered = point.id === hoveredPointId;
                  const isActive = selected || hovered;
                  return (
                    <g
                      key={point.id}
                      style={{ transformOrigin: "center center" }}
                      onClick={() => setSelectedPointId(point.id)}
                      onMouseEnter={(e) => {
                        setHoveredPointId(point.id);
                        if (containerRef.current) {
                          const rect =
                            containerRef.current.getBoundingClientRect();
                          setTooltip({
                            point,
                            x: e.clientX - rect.left,
                            y: e.clientY - rect.top - 10,
                          });
                        }
                      }}
                      onMouseMove={(e) => {
                        if (tooltip && containerRef.current) {
                          const rect =
                            containerRef.current.getBoundingClientRect();
                          const x = Math.min(
                            Math.max(0, e.clientX - rect.left),
                            rect.width - 100,
                          );
                          const y = Math.min(
                            Math.max(0, e.clientY - rect.top - 10),
                            rect.height - 40,
                          );
                          setTooltip((t) => ({ ...t, x, y }));
                        }
                      }}
                      onMouseLeave={() => {
                        setHoveredPointId(null);
                        setTooltip(null);
                      }}
                      className="cursor-pointer"
                    >
                      <circle
                        cx={point.cx}
                        cy={point.cy}
                        r={point.r}
                        fill={
                          isActive
                            ? "rgba(59, 130, 246, 0.55)"
                            : "rgba(56, 189, 248, 0.35)"
                        }
                        stroke={
                          isActive
                            ? "rgb(125, 211, 252)"
                            : "rgba(56, 189, 248, 0.8)"
                        }
                        strokeWidth={1}
                        style={{ transformOrigin: "center center" }}
                        className="transition-colors"
                      >
                        <title>
                          {`Cluster ${point.clusterId}\nsize=${point.size}\nts=${point.ts}\nvalue=${point.value}\nmetrics=${point.metrics.slice(0, 5).join(", ")}${point.metrics.length > 5 ? "..." : ""}`}
                        </title>
                      </circle>
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
                  );
                })}
                <text x="12" y="24" className="fill-sre-text-muted text-[11px]">
                  {chart.labels?.right}
                </text>
                <text
                  x="12"
                  y="145"
                  className="fill-sre-text-muted text-[11px]"
                >
                  {chart.labels?.center}
                </text>
                <text
                  x="12"
                  y="260"
                  className="fill-sre-text-muted text-[11px]"
                >
                  {chart.labels?.left}
                </text>
                <text
                  x="40"
                  y="275"
                  className="fill-sre-text-muted text-[11px]"
                >
                  {chart.labels?.start}
                </text>
                <text
                  x={chart.width - 120}
                  y="275"
                  className="fill-sre-text-muted text-[11px]"
                >
                  {chart.labels?.end}
                </text>
              </svg>
              {tooltip && (
                <div
                  style={{ left: tooltip.x, top: tooltip.y, maxWidth: "200px" }}
                  className="absolute bg-sre-bg-card text-sre-text text-xs p-2 rounded shadow-lg pointer-events-none z-30"
                >
                  <p className="font-semibold">
                    Cluster {tooltip.point.clusterId}
                  </p>
                  <p>Size: {formatNumber(tooltip.point.size)} anomalies</p>
                  <p>Time: {formatTimestamp(tooltip.point.ts)}</p>
                  <p>Value: {formatNumber(tooltip.point.value)}</p>
                  <p className="mt-1 truncate">
                    {tooltip.point.metrics.slice(0, 5).join(", ")}
                    {tooltip.point.metrics.length > 5 ? "..." : ""}
                  </p>
                </div>
              )}
            </div>
          </div>

          {selectedPoint && (
            <div
              className={`${compact ? "" : "border border-sre-border rounded-2xl"} overflow-hidden bg-sre-surface/40`}
            >
              <div className="flex items-center justify-between px-4 py-3 border-b border-sre-border bg-sre-surface/60">
                <div className="flex items-center gap-2.5">
                  <div className="w-2 h-2 rounded-full bg-sre-primary animate-pulse" />
                  <p className="text-sm font-semibold text-sre-text">
                    Cluster {selectedPoint.clusterId}
                  </p>
                </div>
                <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-sre-primary/10 text-sre-primary border border-sre-primary/20">
                  {formatNumber(selectedPoint.size)} anomalies
                </span>
              </div>

              <div className="px-4 py-3 flex items-center gap-6 border-b border-sre-border/60">
                <div className="flex flex-col gap-0.5">
                  <span className="text-[10px] uppercase tracking-widest text-sre-text-muted font-medium">
                    Centroid Time
                  </span>
                  <span className="text-xs font-mono text-sre-text">
                    {formatTimestamp(selectedPoint.ts)}
                  </span>
                </div>
                <div className="w-px h-8 bg-sre-border" />
                <div className="flex flex-col gap-0.5">
                  <span className="text-[10px] uppercase tracking-widest text-sre-text-muted font-medium">
                    Centroid Value
                  </span>
                  <span className="text-xs font-mono text-sre-text">
                    {formatNumber(selectedPoint.value)}
                  </span>
                </div>
              </div>

              <div className="px-4 py-3 flex flex-col gap-2">
                <span className="text-[10px] uppercase tracking-widest text-sre-text-muted font-medium">
                  Affected Metrics
                  <span className="ml-1.5 text-sre-primary normal-case tracking-normal">
                    ({selectedPoint.metrics.length})
                  </span>
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {selectedPoint.metrics.slice(0, 24).map((metric) => (
                    <span
                      key={metric}
                      className="text-xs px-2.5 py-1 rounded-lg bg-sre-surface border border-sre-border text-sre-text hover:border-sre-primary/40 hover:text-sre-primary transition-colors cursor-default"
                    >
                      {metric}
                    </span>
                  ))}
                  {selectedPoint.metrics.length > 24 && (
                    <span className="text-xs px-2.5 py-1 rounded-lg bg-sre-primary/10 border border-sre-primary/20 text-sre-primary font-medium">
                      +{selectedPoint.metrics.length - 24} more
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );

  if (compact) {
    return <div>{content}</div>;
  }

  return <Section>{content}</Section>;
}

RcaClusterPanel.propTypes = {
  report: PropTypes.object,
  compact: PropTypes.bool,
};
