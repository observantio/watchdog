import { useMemo, useState, useEffect, useRef, useCallback } from 'react'
import PropTypes from 'prop-types'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  MarkerType,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { formatDuration } from '../../utils/formatters'
import {
  buildServiceGraphData,
  buildServiceGraphNodes,
  buildServiceGraphInsights,
  buildServiceGraphEdges,
  layoutServiceGraph,
} from '../../utils/serviceGraphUtils'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const STATUS_COLOR = (errorRate, isPain) => {
  if (isPain || errorRate > 5) return { hex: '#ef4444', ring: 'border-red-500/60', bar: 'bg-red-500', soft: 'bg-red-500/10' }
  if (errorRate > 1)           return { hex: '#f59e0b', ring: 'border-yellow-500/40', bar: 'bg-yellow-500', soft: 'bg-yellow-500/10' }
  return                              { hex: '#22c55e', ring: 'border-emerald-500/30', bar: 'bg-emerald-500', soft: 'bg-emerald-500/10' }
}

const EDGE_COLOR = (errorRate) => {
  if (errorRate > 5) return '#ef4444'
  if (errorRate > 1) return '#f59e0b'
  return '#818cf8'
}

// ---------------------------------------------------------------------------
// ServiceNode
// ---------------------------------------------------------------------------
const Stat = ({ label, value, highlight }) => (
  <div className="flex flex-col gap-0.5">
    <span className="text-[10px] text-sre-text-muted uppercase tracking-wider">{label}</span>
    <span className={`text-xs font-semibold tabular-nums ${highlight ?? 'text-sre-text'}`}>{value}</span>
  </div>
)
Stat.propTypes = { label: PropTypes.string, value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]), highlight: PropTypes.string }

const ServiceNode = ({ data }) => {
  const { name, stats, isActive, isHovered } = data
  const isPain     = stats.pain
  const errorRate  = stats.errorRateNum
  const c          = STATUS_COLOR(errorRate, isPain)
  const p95Hi      = stats.p95?.includes('ms') && parseFloat(stats.p95) > 1000 ? 'text-red-400' : undefined
  const errHi      = errorRate > 5 ? 'text-red-400' : errorRate > 1 ? 'text-yellow-400' : 'text-emerald-400'

  return (
    <div className={[
      'relative rounded-2xl border bg-sre-surface/95  px-4 py-3 min-w-[220px] max-w-[260px] shadow-lg transition-all duration-150',
      isActive  ? 'ring-2 ring-sre-primary/70 shadow-xl scale-[1.03]' : '',
      isHovered && !isActive ? 'shadow-xl scale-[1.02]' : '',
      c.ring,
      isActive || isHovered ? 'border-opacity-100' : 'border-sre-border/50',
    ].filter(Boolean).join(' ')}>

      <Handle type="target" position={Position.Left}
        className="!w-2.5 !h-2.5 !border-2 !border-sre-bg !bg-sre-primary/60 hover:!bg-sre-primary transition-colors" />
      <Handle type="source" position={Position.Right}
        className="!w-2.5 !h-2.5 !border-2 !border-sre-bg !bg-sre-primary/60 hover:!bg-sre-primary transition-colors" />

      <div className="flex items-center gap-2 mb-2.5">
        <span className="w-2.5 h-2.5 rounded-full flex-shrink-0"
          style={{ backgroundColor: c.hex, boxShadow: `0 0 7px ${c.hex}bb` }} />
        <span className="font-semibold text-sre-text text-sm truncate flex-1 leading-tight">{name}</span>
        <div className="flex items-center gap-1 flex-shrink-0">
          {stats.inbound  === 0 && <span className="px-1.5 py-0.5 text-[9px] font-bold rounded-full bg-sre-primary/20 text-sre-primary border border-sre-primary/30 uppercase tracking-wide">Entry</span>}
          {stats.outbound === 0 && <span className="px-1.5 py-0.5 text-[9px] font-bold rounded-full bg-sre-surface text-sre-text-muted border border-sre-border/50 uppercase tracking-wide">Leaf</span>}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-x-3 gap-y-2 mb-2.5">
        <Stat label="Traces" value={stats.traces} />
        <Stat label="P50"    value={stats.p50} />
        <Stat label="P95"    value={stats.p95} highlight={p95Hi} />
        <Stat label="Spans"  value={stats.spans} />
        <Stat label="Error"  value={stats.errorRate} highlight={errHi} />
        <Stat label="I/O"    value={`${stats.inbound}/${stats.outbound}`} />
      </div>

      <div className="flex items-center gap-1.5">
        <div className="h-1 flex-1 rounded-full bg-sre-border/30 overflow-hidden">
          <div className={`h-full rounded-full transition-all duration-700 ${c.bar}`}
            style={{ width: `${Math.max(8, 100 - errorRate * 4)}%` }} />
        </div>
        <span className="text-[9px] text-sre-text-muted uppercase tracking-wide">Health</span>
      </div>

      {isPain && (
        <div className={`mt-2 flex items-center gap-1.5 text-[10px] px-2 py-1 rounded-lg ${c.soft} text-red-300 border border-red-500/20`}>
          <span className="material-icons text-[12px]">local_fire_department</span>
          High latency or error rate
        </div>
      )}
    </div>
  )
}
ServiceNode.propTypes = {
  data: PropTypes.shape({ name: PropTypes.string.isRequired, stats: PropTypes.object.isRequired, isActive: PropTypes.bool, isHovered: PropTypes.bool }).isRequired,
}

const NODE_TYPES = { service: ServiceNode }

const toEdges = (rawEdges) =>
  rawEdges.map(e => {
    const color = EDGE_COLOR(e.data?.errorRateNum ?? 0)
    return {
      ...e,
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 12, height: 12 },
      style: { stroke: color, strokeWidth: 1 },
    }
  })

const StatCard = ({ label, children, empty }) => (
  <div className="p-3 rounded-xl border border-sre-border/40 bg-sre-bg/40 flex flex-col gap-1.5 min-w-0">
    <div className="text-[10px] font-semibold uppercase tracking-widest text-sre-text-muted">{label}</div>
    {empty ? <div className="text-xs text-sre-text-muted/60 italic">{empty}</div> : children}
  </div>
)
StatCard.propTypes = { label: PropTypes.string, children: PropTypes.node, empty: PropTypes.string }

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
export default function ServiceGraphAsync({ traces }) {
  const [activeNodeId, setActiveNodeId] = useState(null)
  const [activeEdgeId, setActiveEdgeId] = useState(null)
  const [hoverNodeId,  setHoverNodeId]  = useState(null)

  const hasSpanData = traces?.length > 0 && traces.some(t => t.spans?.length > 1)

  const graphData = useMemo(
    () => hasSpanData ? buildServiceGraphData(traces) : { services: new Map(), edges: new Map() },
    [traces, hasSpanData],
  )

  const structuralNodes = useMemo(() => buildServiceGraphNodes(graphData, null, null), [graphData])
  const structuralEdges = useMemo(() => toEdges(buildServiceGraphEdges(graphData, null, null)), [graphData])
  const insights        = useMemo(() => buildServiceGraphInsights(graphData), [graphData])
  const layouted        = useMemo(() => layoutServiceGraph(structuralNodes, structuralEdges), [structuralNodes, structuralEdges])

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const prevKeyRef = useRef(null)

  // Reset only when topology changes; preserve dragged positions
  useEffect(() => {
    const key = [
      ...Array.from(graphData.services.keys()).sort(),
      '|',
      ...Array.from(graphData.edges.keys()).sort(),
    ].join(',')
    if (prevKeyRef.current === key) return
    const posById = new Map(nodes.map(n => [n.id, n.position]))
    setNodes(layouted.nodes.map(n => {
      const p = posById.get(n.id)
      return p && typeof p.x === 'number' ? { ...n, position: p } : n
    }))
    setEdges(layouted.edges)
    prevKeyRef.current = key
  }, [graphData, layouted, nodes, setNodes, setEdges])

  // Apply active/hover purely as data mutation — never touches position
  useEffect(() => {
    setNodes(prev => prev.map(n => ({
      ...n,
      data: { ...n.data, isActive: n.id === activeNodeId, isHovered: n.id === hoverNodeId },
    })))
  }, [activeNodeId, hoverNodeId, setNodes])

  useEffect(() => {
    setEdges(prev => prev.map(e => {
      const isActive      = e.id === activeEdgeId
      const isHighlighted = activeNodeId ? (e.source === activeNodeId || e.target === activeNodeId) : false
      const dimmed        = (activeEdgeId || activeNodeId) && !isActive && !isHighlighted
      const color         = EDGE_COLOR(e.data?.errorRateNum ?? 0)
      return {
        ...e,
        selected: isActive,
        style: {
          stroke: color,
          strokeWidth: isActive ? 2 : 1,
          opacity: dimmed ? 0.15 : 1,
        },
      }
    }))
  }, [activeEdgeId, activeNodeId, setEdges])

  const handlePaneClick      = useCallback(() => { setActiveNodeId(null); setActiveEdgeId(null) }, [])
  const handleNodeClick      = useCallback((_, n) => { setActiveNodeId(n.id); setActiveEdgeId(null) }, [])
  const handleEdgeClick      = useCallback((_, e) => { setActiveEdgeId(e.id); setActiveNodeId(null) }, [])
  const handleNodeMouseEnter = useCallback((_, n) => setHoverNodeId(n.id), [])
  const handleNodeMouseLeave = useCallback(() => setHoverNodeId(null), [])

  // Minimap: use inline style background so canvas has guaranteed dark bg
  // nodeColor must return a fully-opaque hex — no CSS variables, no opacity
  const miniMapNodeColor = useCallback((node) => {
    const err = node?.data?.stats?.errorRateNum
    if (err == null || Number.isNaN(+err)) return '#94a3b8'
    if (err > 5)  return '#f87171'
    if (err > 1)  return '#fbbf24'
    return '#4ade80'
  }, [])

  if (layouted.nodes.length === 0) {
    return !hasSpanData ? (
      <div className="border-2 border-dashed border-sre-border/40 rounded-2xl p-10 text-center">
        <span className="material-icons text-4xl text-sre-text-muted/40 block mb-3">hub</span>
        <p className="text-sm font-medium text-sre-text mb-1">Full trace data required</p>
        <p className="text-xs text-sre-text-muted max-w-sm mx-auto">
          The service graph needs traces with multiple spans. Try loading individual traces or narrowing your time range.
        </p>
      </div>
    ) : null
  }

  const activeNode = insights.serviceStats.find(s => s.name === activeNodeId)
  const activeEdge = insights.edgeStats.find(e => e.id === activeEdgeId)

  return (
    <>
      <style>{`
        .react-flow__minimap {
          background: #727272 !important;
          border-radius: 10px !important;
          overflow: hidden;
        }
        .react-flow__minimap svg {
          background: #727272 !important;
        }
        .react-flow__minimap-mask {
          fill: #727272 !important;
        }
        .react-flow__minimap-node {
          stroke: none !important;
        }

        /* dark mode: use a white background for better contrast */
        .dark .react-flow__minimap,
        .dark .react-flow__minimap svg {
          background: #ffffff !important;
        }
        .dark .react-flow__minimap-mask {
          fill: #ffffff !important;
        }
      `}</style>

      <div className="flex flex-col gap-3">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-sre-primary/15 border border-sre-primary/20 flex items-center justify-center">
              <span className="material-icons text-sre-primary text-sm">hub</span>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-sre-text leading-none">Service Dependency Map</h3>
              <p className="text-[11px] text-sre-text-muted mt-0.5">Pain points highlighted</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-sre-text-muted bg-sre-surface/80 px-2.5 py-1 rounded-lg border border-sre-border/40">{nodes.length} services</span>
            <span className="text-[11px] text-sre-text-muted bg-sre-surface/80 px-2.5 py-1 rounded-lg border border-sre-border/40">{edges.length} connections</span>
          </div>
        </div>

        {/* Insights + Selection */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_240px] gap-3">
          <div className="grid grid-cols-3 gap-2">
            <StatCard label="Top Pain Services" empty={!insights.painServices.length ? 'No pain points' : undefined}>
              {insights.painServices.map(s => (
                <button key={s.name} type="button"
                  onClick={() => { setActiveNodeId(s.name); setActiveEdgeId(null) }}
                  className="flex items-center justify-between gap-2 text-xs hover:text-sre-primary transition-colors w-full text-left">
                  <span className="text-sre-text truncate">{s.name}</span>
                  <span className="text-red-400 flex-shrink-0 tabular-nums">{formatDuration(s.p95)}</span>
                </button>
              ))}
            </StatCard>
            <StatCard label="Busiest Flows" empty={!insights.topCalls.length ? 'No flows' : undefined}>
              {insights.topCalls.map(e => (
                <button key={e.id} type="button"
                  onClick={() => { setActiveEdgeId(e.id); setActiveNodeId(null) }}
                  className="flex items-center justify-between gap-2 text-xs hover:text-sre-primary transition-colors w-full text-left">
                  <span className="text-sre-text truncate">{e.source} → {e.target}</span>
                  <span className="text-sre-text-muted flex-shrink-0 tabular-nums">{e.count}</span>
                </button>
              ))}
            </StatCard>
            <StatCard label="Highest Error Rate" empty={!insights.topErrors.length ? 'No errors' : undefined}>
              {insights.topErrors.map(e => (
                <button key={e.id} type="button"
                  onClick={() => { setActiveEdgeId(e.id); setActiveNodeId(null) }}
                  className="flex items-center justify-between gap-2 text-xs hover:text-sre-primary transition-colors w-full text-left">
                  <span className="text-sre-text truncate">{e.source} → {e.target}</span>
                  <span className="text-yellow-400 flex-shrink-0 tabular-nums">{e.errorRateNum.toFixed(1)}%</span>
                </button>
              ))}
            </StatCard>
          </div>

          <div className="p-3 rounded-xl border border-sre-border/40 bg-sre-bg/40 flex flex-col gap-1.5">
            <div className="text-[10px] font-semibold uppercase tracking-widest text-sre-text-muted">Selection</div>
            {activeNode && (
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: STATUS_COLOR(activeNode.errorRateNum, activeNode.pain).hex }} />
                  <span className="text-sm font-semibold text-sre-text truncate">{activeNode.name}</span>
                </div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
                  <Stat label="Traces" value={activeNode.traces} />
                  <Stat label="Spans"  value={activeNode.spans} />
                  <Stat label="P95"    value={formatDuration(activeNode.p95)} />
                  <Stat label="Error"  value={`${activeNode.errorRateNum.toFixed(1)}%`} />
                  <Stat label="In/Out" value={`${activeNode.inbound}/${activeNode.outbound}`} />
                </div>
              </div>
            )}
            {activeEdge && (
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-semibold text-sre-text truncate">{activeEdge.source} → {activeEdge.target}</span>
                <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
                  <Stat label="Calls" value={activeEdge.count} />
                  <Stat label="P95"   value={formatDuration(activeEdge.p95)} />
                  <Stat label="Error" value={`${activeEdge.errorRateNum.toFixed(1)}%`} />
                </div>
              </div>
            )}
            {!activeNode && !activeEdge && (
              <p className="text-xs text-sre-text-muted/60 italic mt-1">Click a node or edge to inspect.</p>
            )}
          </div>
        </div>

        {/* Canvas */}
        <div className="rounded-2xl overflow-hidden border border-sre-border/50" style={{ height: 560 }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodeTypes={NODE_TYPES}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.1}
            maxZoom={2.5}
            defaultViewport={{ x: 0, y: 0, zoom: 0.85 }}
            onPaneClick={handlePaneClick}
            onNodeClick={handleNodeClick}
            onEdgeClick={handleEdgeClick}
            onNodeMouseEnter={handleNodeMouseEnter}
            onNodeMouseLeave={handleNodeMouseLeave}
            proOptions={{ hideAttribution: true }}
          >
            {/*
              Minimap fix:
              - background is set via inline style to a guaranteed solid hex (no CSS var)
              - nodeColor returns solid hex strings — the MiniMap canvas cannot resolve
                Tailwind CSS variables or rgba() reliably
              - nodeStrokeWidth=0 removes the stroke that can obscure small nodes
              - maskColor is semi-transparent so viewport rect is visible but nodes show through
            */}
            <MiniMap
              zoomable
              pannable
              width={210}
              height={140}
              nodeColor={miniMapNodeColor}
              nodeStrokeWidth={0}
              nodeBorderRadius={3}
              maskColor="rgba(15,23,42,0.55)"
            />
            <Controls showZoom showFitView showInteractive />
            <Background gap={24} size={1} color="rgba(255,255,255,0.03)" variant="dots" />
          </ReactFlow>
        </div>

        {/* Legend */}
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-5 text-[11px] text-sre-text-muted">
            {[
              { color: '#4ade80', label: 'Healthy' },
              { color: '#fbbf24', label: 'Warning' },
              { color: '#f87171', label: 'Pain Point' },
            ].map(({ color, label }) => (
              <div key={label} className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                {label}
              </div>
            ))}
            <div className="flex items-center gap-1.5">
              <svg width="22" height="8" viewBox="0 0 22 8" fill="none">
                <defs>
                  <linearGradient id="lgFlow" x1="0" x2="1">
                    <stop offset="0%"   stopColor="#4ade80" />
                    <stop offset="50%"  stopColor="#6366f1" />
                    <stop offset="100%" stopColor="#f87171" />
                  </linearGradient>
                  <marker id="lgArrow" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto">
                    <path d="M0,0.5 L4.5,2.5 L0,4.5 Z" fill="url(#lgFlow)" />
                  </marker>
                </defs>
                <line x1="0" y1="4" x2="17" y2="4" stroke="url(#lgFlow)" strokeWidth="2.5" markerEnd="url(#lgArrow)" />
              </svg>
              Flow direction
            </div>
          </div>
          <span className="text-[10px] text-sre-text-muted/50">Edge labels: calls · p95 · error%</span>
        </div>

      </div>
    </>
  )
}

ServiceGraphAsync.propTypes = {
  traces: PropTypes.arrayOf(PropTypes.object).isRequired,
}
