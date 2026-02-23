import { useMemo } from 'react'
import dagre from '@dagrejs/dagre'
import PropTypes from 'prop-types'
import ReactFlow, { Background, Controls, MarkerType, MiniMap } from 'reactflow'
import 'reactflow/dist/style.css'
import { Card } from '../ui'

function buildTopologyGraph(topology) {
  const root = topology?.root_service || ''
  const downstream = Array.isArray(topology?.affected_downstream) ? topology.affected_downstream : []
  const upstream = Array.isArray(topology?.upstream_roots) ? topology.upstream_roots : []
  const allServices = Array.isArray(topology?.all_services) ? topology.all_services : []

  const serviceSet = new Set([root, ...downstream, ...upstream, ...allServices].filter(Boolean))
  const all = [...serviceSet]
  if (all.length === 0) {
    return { nodes: [], edges: [] }
  }

  const related = all.filter((service) => service !== root && !downstream.includes(service) && !upstream.includes(service))
  const nodes = all.map((service) => {
    const role = service === root ? 'root' : downstream.includes(service) ? 'downstream' : upstream.includes(service) ? 'upstream' : 'related'
    const style = {
      root: { bg: 'rgba(59, 130, 246, 0.20)', border: 'rgba(59, 130, 246, 0.9)' },
      downstream: { bg: 'rgba(239, 68, 68, 0.18)', border: 'rgba(239, 68, 68, 0.85)' },
      upstream: { bg: 'rgba(34, 197, 94, 0.18)', border: 'rgba(34, 197, 94, 0.85)' },
      related: { bg: 'rgba(148, 163, 184, 0.16)', border: 'rgba(148, 163, 184, 0.7)' },
    }[role]

    return {
      id: service,
      position: { x: 0, y: 0 },
      data: { label: service },
      style: {
        width: 190,
        borderRadius: 14,
        border: `1px solid ${style.border}`,
        background: style.bg,
        color: 'var(--sre-text)',
        fontSize: 12,
        fontWeight: 600,
        padding: 8,
        boxShadow: '0 2px 10px rgba(0,0,0,0.2)',
      },
    }
  })

  const edges = []
  const pushEdge = (source, target, kind) => {
    if (!source || !target || source === target) return
    edges.push({
      id: `${source}->${target}`,
      source,
      target,
      type: 'smoothstep',
      animated: kind !== 'related',
      label: kind,
      markerEnd: { type: MarkerType.ArrowClosed, color: 'rgba(148, 163, 184, 0.9)' },
      style: {
        stroke: kind === 'downstream' ? '#ef4444' : kind === 'upstream' ? '#22c55e' : '#94a3b8',
        strokeWidth: kind === 'related' ? 1.2 : 1.8,
        strokeDasharray: kind === 'related' ? '6 4' : '0',
      },
      labelStyle: {
        fill: 'var(--sre-text-muted)',
        fontSize: 10,
        fontWeight: 500,
      },
      labelBgStyle: {
        fill: 'var(--sre-surface)',
        fillOpacity: 0.92,
        stroke: 'var(--sre-border)',
        rx: 4,
      },
    })
  }

  upstream.forEach((service) => pushEdge(service, root, 'upstream'))
  downstream.forEach((service) => pushEdge(root, service, 'downstream'))
  related.forEach((service) => pushEdge(root, service, 'related'))

  const graph = new dagre.graphlib.Graph()
  graph.setGraph({ rankdir: 'LR', nodesep: 70, ranksep: 120, marginx: 20, marginy: 20 })
  graph.setDefaultEdgeLabel(() => ({}))

  nodes.forEach((node) => graph.setNode(node.id, { width: 190, height: 62 }))
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target))
  dagre.layout(graph)

  const positionedNodes = nodes.map((node) => {
    const dagreNode = graph.node(node.id)
    return {
      ...node,
      position: {
        x: dagreNode.x - 95,
        y: dagreNode.y - 31,
      },
    }
  })
  return { nodes: positionedNodes, edges }
}

export default function RcaTopologyPanel({ topology }) {
  const graph = useMemo(() => buildTopologyGraph(topology), [topology])

  if (!topology || graph.nodes.length === 0) {
    return (
      <Card className="border border-sre-border p-4">
        <h3 className="text-lg text-sre-text font-semibold mb-3">Topology</h3>
        <p className="text-sm text-sre-text-muted">Topology data not available for this report.</p>
      </Card>
    )
  }

  return (
    <Card className="border border-sre-border p-4">
      <h3 className="text-lg text-sre-text font-semibold mb-1">Topology and Blast Radius</h3>
      <p className="text-sm text-sre-text-muted mb-3">
        Root service: <span className="text-sre-text font-semibold">{topology.root_service || 'n/a'}</span>
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
        <div className="rounded-lg border border-sre-border bg-sre-surface/25 p-2">
          <p className="text-[11px] uppercase tracking-wide text-sre-text-muted">Downstream</p>
          <p className="text-sm text-sre-text font-semibold">{(topology.affected_downstream || []).length}</p>
        </div>
        <div className="rounded-lg border border-sre-border bg-sre-surface/25 p-2">
          <p className="text-[11px] uppercase tracking-wide text-sre-text-muted">Upstream Roots</p>
          <p className="text-sm text-sre-text font-semibold">{(topology.upstream_roots || []).length}</p>
        </div>
        <div className="rounded-lg border border-sre-border bg-sre-surface/25 p-2">
          <p className="text-[11px] uppercase tracking-wide text-sre-text-muted">Services</p>
          <p className="text-sm text-sre-text font-semibold">{(topology.all_services || []).length}</p>
        </div>
        <div className="rounded-lg border border-sre-border bg-sre-surface/25 p-2">
          <p className="text-[11px] uppercase tracking-wide text-sre-text-muted">Graph Edges</p>
          <p className="text-sm text-sre-text font-semibold">{graph.edges.length}</p>
        </div>
      </div>

      <div className="h-[430px] rounded-xl border border-sre-border overflow-hidden">
        <ReactFlow
          nodes={graph.nodes}
          edges={graph.edges}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          proOptions={{ hideAttribution: true }}
          nodesConnectable={false}
          nodesDraggable={false}
          elementsSelectable
          panOnDrag
          zoomOnScroll
        >
          <MiniMap
            pannable
            zoomable
            nodeStrokeColor={() => 'rgba(148, 163, 184, 0.8)'}
            nodeColor={() => 'rgba(148, 163, 184, 0.7)'}
            maskColor="rgba(15, 23, 42, 0.4)"
          />
          <Controls showZoom showFitView showInteractive />
          <Background gap={28} size={1} color="rgba(148,163,184,0.20)" variant="dots" />
        </ReactFlow>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-xs text-sre-text-muted">
        <span className="px-2 py-1 rounded-md border border-sre-border bg-sre-primary/10 text-sre-primary">Root</span>
        <span className="px-2 py-1 rounded-md border border-sre-border bg-red-500/10 text-red-300">Downstream</span>
        <span className="px-2 py-1 rounded-md border border-sre-border bg-emerald-500/10 text-emerald-300">Upstream Root</span>
        <span className="px-2 py-1 rounded-md border border-sre-border bg-slate-400/10 text-slate-300">Related Service</span>
      </div>
    </Card>
  )
}

RcaTopologyPanel.propTypes = {
  topology: PropTypes.object,
}
