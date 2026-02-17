import { useMemo, useState } from 'react'
import PropTypes from 'prop-types'
import ReactFlow, { Background, Controls, MiniMap, Handle, Position } from 'reactflow'
import 'reactflow/dist/style.css'
import { formatDuration } from '../../utils/formatters'
import {
  buildServiceGraphData,
  buildServiceGraphNodes,
  buildServiceGraphInsights,
  buildServiceGraphEdges,
  layoutServiceGraph,
} from '../../utils/serviceGraphUtils'

const ServiceNode = ({ data }) => {
  const { name, stats, colorClass } = data
  const isPain = stats.pain
  const errorRate = stats.errorRateNum

  return (
    <div className={`rounded-xl border-2 bg-gradient-to-br from-sre-surface to-sre-surface/80 px-4 py-3 shadow-lg min-w-[240px] transition-all duration-300 hover:shadow-xl hover:scale-105 ${colorClass} ${isPain ? 'border-red-500/50' : 'border-sre-border'}`}>
      <Handle type="target" position={Position.Left} className="!bg-sre-primary/70 !w-3 !h-3 !border-2 !border-sre-bg hover:!bg-sre-primary hover:!scale-110 transition-all" />
      <Handle type="source" position={Position.Right} className="!bg-sre-primary/70 !w-3 !h-3 !border-2 !border-sre-bg hover:!bg-sre-primary hover:!scale-110 transition-all" />

      <div className="flex items-center gap-2 mb-3">
        <div className={`w-3 h-3 rounded-full ${isPain ? 'bg-red-500' : errorRate > 1 ? 'bg-yellow-500' : 'bg-green-500'} animate-pulse`}></div>
        <div className="font-bold text-sre-text truncate flex-1">{name}</div>
        {isPain && <span className="material-icons text-red-500 text-sm animate-bounce">warning</span>}
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="flex justify-between">
          <span className="text-sre-text-muted">Traces:</span>
          <span className="text-sre-text font-medium">{stats.traces}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-sre-text-muted">Spans:</span>
          <span className="text-sre-text font-medium">{stats.spans}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-sre-text-muted">P50:</span>
          <span className="text-sre-text font-medium">{stats.p50}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-sre-text-muted">P95:</span>
          <span className={`font-medium ${stats.p95.includes('ms') && parseFloat(stats.p95) > 1000 ? 'text-red-400' : 'text-sre-text'}`}>{stats.p95}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-sre-text-muted">Error:</span>
          <span className={`font-medium ${errorRate > 5 ? 'text-red-400' : errorRate > 1 ? 'text-yellow-400' : 'text-green-400'}`}>{stats.errorRate}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-sre-text-muted">I/O:</span>
          <span className="text-sre-text font-medium">{stats.inbound}/{stats.outbound}</span>
        </div>
      </div>

      {isPain && (
        <div className="mt-3 text-[10px] px-2 py-1.5 rounded-lg bg-gradient-to-r from-red-500/20 to-red-600/20 text-red-300 border border-red-500/30 animate-pulse">
          <span className="material-icons text-xs mr-1 align-middle">local_fire_department</span>
          Pain point: high latency or error rate
        </div>
      )}

      <div className="mt-2 flex items-center gap-1">
        <div className={`h-1.5 flex-1 rounded-full ${isPain ? 'bg-red-500/20' : errorRate > 1 ? 'bg-yellow-500/20' : 'bg-green-500/20'}`}>
          <div
            className={`h-full rounded-full transition-all duration-1000 ${isPain ? 'bg-red-500' : errorRate > 1 ? 'bg-yellow-500' : 'bg-green-500'}`}
            style={{ width: `${Math.max(10, 100 - errorRate * 2)}%` }}
          ></div>
        </div>
        <span className="text-[10px] text-sre-text-muted">Health</span>
      </div>
    </div>
  )
}

ServiceNode.propTypes = {
  data: PropTypes.shape({
    name: PropTypes.string.isRequired,
    stats: PropTypes.object.isRequired,
    colorClass: PropTypes.string.isRequired,
  }).isRequired,
}

export default function ServiceGraphAsync({ traces }) {
  const [activeNodeId, setActiveNodeId] = useState(null)
  const [activeEdgeId, setActiveEdgeId] = useState(null)
  const [hoverNodeId, setHoverNodeId] = useState(null)

  const graphData = useMemo(() => buildServiceGraphData(traces), [traces])

  const nodes = useMemo(
    () => buildServiceGraphNodes(graphData, activeNodeId, hoverNodeId),
    [graphData, activeNodeId, hoverNodeId]
  )

  const insights = useMemo(() => buildServiceGraphInsights(graphData), [graphData])

  const edges = useMemo(
    () => buildServiceGraphEdges(graphData, activeEdgeId, activeNodeId),
    [graphData, activeEdgeId, activeNodeId]
  )

  const layouted = useMemo(() => layoutServiceGraph(nodes, edges), [nodes, edges])

  if (layouted.nodes.length === 0) return null

  const activeNode = insights.serviceStats.find(s => s.name === activeNodeId)
  const activeEdge = insights.edgeStats.find(e => e.id === activeEdgeId)
  const activeDirection = activeEdge ? `${activeEdge.source} → ${activeEdge.target}` : null

  return (
    <div className="bg-gradient-to-br from-sre-surface/30 to-sre-surface/10 border-2 border-sre-border/50 rounded-xl p-6 shadow-lg">
      {/* (content copied from original) */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-bold text-sre-text flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-sre-primary to-sre-primary-light flex items-center justify-center">
            <span className="material-icons text-white text-sm">hub</span>
          </div>
          Service Dependency Map
          <span className="text-sm font-normal text-sre-text-muted">(pain points highlighted)</span>
        </h3>
        <div className="flex items-center gap-2">
          <div className="text-xs text-sre-text-muted bg-sre-surface px-2 py-1 rounded-lg border">
            {layouted.nodes.length} services • {layouted.edges.length} connections
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 mb-4">
        <div className="p-4 bg-sre-surface/60 rounded-xl border border-sre-border/60">
          <div className="text-xs text-sre-text-muted mb-2">Insights</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div className="p-3 rounded-lg border border-sre-border/50 bg-sre-surface/60">
              <div className="text-sre-text-muted mb-1">Top Pain Services</div>
              {insights.painServices.length ? insights.painServices.map(s => (
                <div key={s.name} className="flex items-center justify-between text-sre-text">
                  <button
                    type="button"
                    onClick={() => { setActiveNodeId(s.name); setActiveEdgeId(null) }}
                    className="truncate hover:text-sre-primary"
                  >
                    {s.name}
                  </button>
                  <span className="text-red-400">{formatDuration(s.p95)}</span>
                </div>
              )) : (
                <div className="text-sre-text-muted">No pain points</div>
              )}
            </div>
            <div className="p-3 rounded-lg border border-sre-border/50 bg-sre-surface/60">
              <div className="text-sre-text-muted mb-1">Busiest Flows</div>
              {insights.topCalls.length ? insights.topCalls.map(e => (
                <div key={e.id} className="flex items-center justify-between text-sre-text">
                  <button
                    type="button"
                    onClick={() => { setActiveEdgeId(e.id); setActiveNodeId(null) }}
                    className="truncate hover:text-sre-primary"
                  >
                    {e.source} → {e.target}
                  </button>
                  <span className="text-sre-text-muted">{e.count}</span>
                </div>
              )) : (
                <div className="text-sre-text-muted">No flows</div>
              )}
            </div>
            <div className="p-3 rounded-lg border border-sre-border/50 bg-sre-surface/60">
              <div className="text-sre-text-muted mb-1">Highest Error Rate</div>
              {insights.topErrors.length ? insights.topErrors.map(e => (
                <div key={e.id} className="flex items-center justify-between text-sre-text">
                  <button
                    type="button"
                    onClick={() => { setActiveEdgeId(e.id); setActiveNodeId(null) }}
                    className="truncate hover:text-sre-primary"
                  >
                    {e.source} → {e.target}
                  </button>
                  <span className="text-yellow-400">{e.errorRateNum.toFixed(1)}%</span>
                </div>
              )) : (
                <div className="text-sre-text-muted">No errors</div>
              )}
            </div>
          </div>
        </div>
        <div className="p-4 bg-sre-surface/60 rounded-xl border border-sre-border/60">
          <div className="text-xs text-sre-text-muted mb-2">Selection</div>
          {activeNode && (
            <div className="text-sm text-sre-text space-y-1">
              <div className="font-semibold">{activeNode.name}</div>
              <div className="text-xs text-sre-text-muted">Traces: {activeNode.traces} · Spans: {activeNode.spans}</div>
              <div className="text-xs text-sre-text-muted">P95: {formatDuration(activeNode.p95)} · Error: {activeNode.errorRateNum.toFixed(1)}%</div>
              <div className="text-xs text-sre-text-muted">Inbound: {activeNode.inbound} · Outbound: {activeNode.outbound}</div>
            </div>
          )}
          {activeEdge && (
            <div className="text-sm text-sre-text space-y-1">
              <div className="font-semibold">{activeEdge.source} → {activeEdge.target}</div>
              <div className="text-xs text-sre-text-muted">Direction: {activeDirection}</div>
              <div className="text-xs text-sre-text-muted">Calls: {activeEdge.count}</div>
              <div className="text-xs text-sre-text-muted">P95: {formatDuration(activeEdge.p95)} · Error: {activeEdge.errorRateNum.toFixed(1)}%</div>
            </div>
          )}
          {!activeNode && !activeEdge && (
            <div className="text-xs text-sre-text-muted">Click a node or edge to focus and see details.</div>
          )}
        </div>
      </div>

      <div className="h-[600px] rounded-xl overflow-hidden border-2 border-sre-border bg-gradient-to-br from-sre-bg to-sre-surface/20 shadow-inner">
        <ReactFlow
          nodes={layouted.nodes}
          edges={layouted.edges}
          nodeTypes={{ service: ServiceNode }}
          fitView
          minZoom={0.1}
          maxZoom={2}
          defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
          className="react-flow-interactive"
          onPaneClick={() => { setActiveNodeId(null); setActiveEdgeId(null) }}
          onNodeClick={(_, node) => {
            setActiveNodeId(node.id)
            setActiveEdgeId(null)
          }}
          onEdgeClick={(_, edge) => {
            setActiveEdgeId(edge.id)
            setActiveNodeId(null)
          }}
          onNodeMouseEnter={(_, node) => setHoverNodeId(node.id)}
          onNodeMouseLeave={() => setHoverNodeId(null)}
        >
          <MiniMap
            zoomable
            pannable
            nodeColor="#1f2937"
            maskColor="rgba(0, 0, 0, 0.2)"
            style={{ background: 'var(--sre-surface)' }}
          />
          <Controls
            showZoom
            showFitView
            showInteractive
            className="react-flow-controls-custom"
          />
          <Background
            gap={20}
            color="var(--sre-border)"
            variant="dots"
          />
        </ReactFlow>
      </div>

      <div className="mt-4 p-4 bg-sre-surface/50 rounded-lg border border-sre-border/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-6 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-green-500 animate-pulse"></div>
              <span className="text-sre-text-muted">Healthy</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-yellow-500 animate-pulse"></div>
              <span className="text-sre-text-muted">Warning</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-red-500 animate-bounce"></div>
              <span className="text-sre-text-muted">Pain Point</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-0.5 bg-gradient-to-r from-green-500 via-yellow-500 to-red-500 rounded"></div>
              <span className="text-sre-text-muted">Flow Direction</span>
            </div>
          </div>
          <div className="text-xs text-sre-text-muted">
            Edge labels: call count • p95 latency • error rate • animated direction
          </div>
        </div>
      </div>
    </div>
  )
}

ServiceGraphAsync.propTypes = {
  traces: PropTypes.arrayOf(PropTypes.object).isRequired,
}
