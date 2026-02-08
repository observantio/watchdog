/**
 * ServiceGraph component for visualizing service dependencies
 * @module components/tempo/ServiceGraph
 */

import { useMemo } from 'react'
import PropTypes from 'prop-types'
import ReactFlow, { Background, Controls, MiniMap, Handle, Position, MarkerType } from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from '@dagrejs/dagre'
import { getServiceName, getSpanAttribute, percentile } from '../../utils/helpers'
import { formatDuration } from '../../utils/formatters'

const PAIN_P95_THRESHOLD_US = 1_000_000
const WARN_P95_THRESHOLD_US = 300_000

/**=
 * ServiceNode component for rendering service nodes in the graph
 * @param {object} props - Component props
 * @param {object} props.data - Node data
*/

const ServiceNode = ({ data }) => {
  const { name, stats, colorClass } = data
  return (
    <div className={`rounded-xl border border-sre-border bg-sre-surface px-4 py-3 shadow-lg min-w-[220px] ${colorClass}`}>
      <Handle type="target" position={Position.Left} className="!bg-sre-primary/70 !w-2 !h-2" />
      <Handle type="source" position={Position.Right} className="!bg-sre-primary/70 !w-2 !h-2" />
      <div className="flex items-center gap-2 mb-2">
        <span className="material-icons text-sre-primary">hub</span>
        <div className="font-semibold text-sre-text truncate">{name}</div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs text-sre-text-muted">
        <div>Traces: <span className="text-sre-text">{stats.traces}</span></div>
        <div>Spans: <span className="text-sre-text">{stats.spans}</span></div>
        <div>P50: <span className="text-sre-text">{stats.p50}</span></div>
        <div>P95: <span className="text-sre-text">{stats.p95}</span></div>
        <div>Error: <span className={stats.errorRateNum > 5 ? 'text-red-400' : 'text-green-400'}>{stats.errorRate}</span></div>
        <div>In/Out: <span className="text-sre-text">{stats.inbound}/{stats.outbound}</span></div>
      </div>
      {stats.pain && (
        <div className="mt-2 text-[10px] px-2 py-1 rounded bg-red-500/10 text-red-400 border border-red-500/30">
          Pain point: high latency or error rate
        </div>
      )}
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

/**
 * Helper: determine if a span indicates an error
 * @param {object} span
 * @returns {boolean}
 */
function spanHasError(span) {
  return Boolean(span.tags?.find(t => t.key === 'error' && t.value === true) || span.status?.code === 'ERROR')
}

/**
 * Helper: find a parent span by id
 * @param {Array} spans
 * @param {string} parentId
 * @returns {object|undefined}
 */
function findParentSpanById(spans, parentId) {
  return spans.find(s => (s.spanId || s.spanID) === parentId)
}

/**
 * Helper: find the root span in a span list
 * @param {Array} spans
 * @returns {object}
 */
function findRootSpan(spans) {
  return spans.find(s => !(s.parentSpanId || s.parentSpanID)) || spans[0]
}

/**
 * ServiceGraph component
 * @param {object} props - Component props
 * @param {Array} props.traces - Array of trace objects
 */
export default function ServiceGraph({ traces }) {
  const graphData = useMemo(() => {
    const services = new Map()
    const edges = new Map()

    const addEdge = (source, target, duration = 0, hasError = false, count = 1) => {
      if (!source || !target || source === target) return
      const key = `${source}->${target}`
      const edge = edges.get(key) || { count: 0, durations: [], errors: 0 }
      edge.count += count
      if (duration > 0) edge.durations.push(duration)
      if (hasError) edge.errors += 1
      edges.set(key, edge)
    }

    traces.forEach(trace => {
      if (!trace.spans) return
      const spans = trace.spans
      const localEdges = new Map()

      const addLocalEdge = (source, target, duration = 0, hasError = false, count = 1) => {
        if (!source || !target || source === target) return
        const key = `${source}->${target}`
        const edge = localEdges.get(key) || { count: 0, durations: [], errors: 0 }
        edge.count += count
        if (duration > 0) edge.durations.push(duration)
        if (hasError) edge.errors += 1
        localEdges.set(key, edge)
      }

      spans.forEach(span => {
        const serviceName = getServiceName(span)
        if (!services.has(serviceName)) {
          services.set(serviceName, { spans: 0, errors: 0, durations: [], traces: new Set(), inbound: 0, outbound: 0 })
        }
        const stats = services.get(serviceName)
        stats.spans += 1
        stats.traces.add(trace.traceID || trace.traceId || '')
        const duration = Number(span.duration || 0)
        if (duration > 0) stats.durations.push(duration)
        const hasError = spanHasError(span)
        if (hasError) stats.errors += 1

        const parentId = span.parentSpanId || span.parentSpanID
        if (parentId) {
          const parentSpan = findParentSpanById(spans, parentId)
          if (parentSpan) {
            const parentService = getServiceName(parentSpan)
            addLocalEdge(parentService, serviceName, duration, hasError, 1)
          }
        }

        const peerServiceRaw = getSpanAttribute(span, [
          'peer.service',
          'peer.service.name',
          'rpc.service',
          'rpc.system',
          'server.address',
          'server.name'
        ])
        const peerService = peerServiceRaw ? String(peerServiceRaw) : null
        if (peerService && peerService !== serviceName) {
          if (!services.has(peerService)) {
            services.set(peerService, { spans: 0, errors: 0, durations: [], traces: new Set(), inbound: 0, outbound: 0 })
          }
          addLocalEdge(serviceName, peerService, duration, hasError, 1)
        }
      })

      if (localEdges.size === 0 && spans.length > 1) {
        const rootSpan = findRootSpan(spans)
        const rootService = getServiceName(rootSpan)
        const servicesInTrace = new Set(spans.map(s => getServiceName(s)).filter(Boolean))
        servicesInTrace.delete(rootService)
        servicesInTrace.forEach((svc) => {
          addLocalEdge(rootService, svc, 0, false, 1)
        })
      }

      for (const [key, val] of localEdges.entries()) {
        const [src, dst] = key.split('->')
        addEdge(src, dst, 0, false, 0)
        const edge = edges.get(key)
        edge.count += val.count
        edge.durations.push(...val.durations)
        edge.errors += val.errors
        edges.set(key, edge)
      }
    })

    // Compute inbound/outbound
    for (const [key, val] of edges.entries()) {
      const [src, dst] = key.split('->')
      if (services.has(src)) services.get(src).outbound += val.count
      if (services.has(dst)) services.get(dst).inbound += val.count
    }

    return { services, edges }
  }, [traces])

  const nodes = useMemo(() => {
    const nodesArray = []
    const entries = Array.from(graphData.services.entries()).sort((a, b) => a[0].localeCompare(b[0]))
    entries.forEach(([name, stats]) => {
      const p50 = percentile(stats.durations, 0.5)
      const p95 = percentile(stats.durations, 0.95)
      const errorRateNum = stats.spans ? (stats.errors / stats.spans) * 100 : 0
      const pain = p95 > PAIN_P95_THRESHOLD_US || errorRateNum > 5
      let colorClass
      if (pain) {
        colorClass = 'ring-2 ring-red-500/60'
      } else if (p95 > WARN_P95_THRESHOLD_US || errorRateNum > 1) {
        colorClass = 'ring-2 ring-yellow-400/60'
      } else {
        colorClass = 'ring-2 ring-green-500/40'
      }
      nodesArray.push({
        id: name,
        type: 'service',
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        position: { x: 0, y: 0 },
        data: {
          name,
          colorClass,
          stats: {
            spans: stats.spans,
            traces: stats.traces.size,
            p50: formatDuration(p50),
            p95: formatDuration(p95),
            errorRate: `${errorRateNum.toFixed(1)}%`,
            errorRateNum,
            inbound: stats.inbound,
            outbound: stats.outbound,
            pain
          }
        }
      })
    })
    return nodesArray
  }, [graphData.services])

  const edges = useMemo(() => {
    return Array.from(graphData.edges.entries()).map(([key, val]) => {
      const [source, target] = key.split('->')
      const p95 = percentile(val.durations, 0.95)
      const errorRateNum = val.count ? (val.errors / val.count) * 100 : 0
      const isPain = p95 > PAIN_P95_THRESHOLD_US || errorRateNum > 5
      let color
      if (isPain) {
        color = '#ef4444'
      } else if (p95 > WARN_P95_THRESHOLD_US || errorRateNum > 1) {
        color = '#f59e0b'
      } else {
        color = '#10b981'
      }
      const label = `${val.count} calls · p95 ${formatDuration(p95)} · err ${errorRateNum.toFixed(1)}%`
      return {
        id: key,
        source,
        target,
        label,
        animated: isPain,
        type: 'smoothstep',
        style: { stroke: color, strokeWidth: isPain ? 2.5 : 1.5 },
        labelStyle: { fill: '#cbd5e1', fontSize: 10 },
        labelBgStyle: { fill: '#0f172a', fillOpacity: 0.7 },
        markerEnd: { type: MarkerType.ArrowClosed, color }
      }
    })
  }, [graphData.edges])

  const layouted = useMemo(() => {
    const nodeWidth = 260
    const nodeHeight = 140

    const g = new dagre.graphlib.Graph()
    g.setDefaultEdgeLabel(() => ({}))
    g.setGraph({
      rankdir: 'LR',
      ranker: 'tight-tree',
      nodesep: 80,
      ranksep: 140,
      edgesep: 20,
      marginx: 20,
      marginy: 20
    })

    nodes.forEach((n) => {
      g.setNode(n.id, { width: nodeWidth, height: nodeHeight })
    })

    edges.forEach((e) => {
      if (e.source && e.target) g.setEdge(e.source, e.target)
    })

    dagre.layout(g)

    const layoutedNodes = nodes.map((n) => {
      const pos = g.node(n.id)
      return {
        ...n,
        position: { x: pos.x - nodeWidth / 2, y: pos.y - nodeHeight / 2 },
        style: { width: nodeWidth, height: nodeHeight }
      }
    })

    return { nodes: layoutedNodes, edges }
  }, [nodes, edges])

  if (layouted.nodes.length === 0) return null

  return (
    <div className="bg-sre-surface/30 border border-sre-border rounded-lg p-6">
      <h3 className="text-lg font-semibold text-sre-text mb-4 flex items-center gap-2">
        <span className="material-icons text-sre-primary">hub</span> Service Dependency Map (pain points highlighted)
      </h3>
      <div className="h-[520px] rounded-lg overflow-hidden border border-sre-border bg-sre-bg">
        <ReactFlow
          nodes={layouted.nodes}
          edges={layouted.edges}
          nodeTypes={{ service: ServiceNode }}
          fitView
          minZoom={0.2}
          maxZoom={1.5}
        >
          <MiniMap zoomable pannable />
          <Controls />
          <Background gap={16} />
        </ReactFlow>
      </div>
      <div className="mt-3 text-xs text-sre-text-muted">
        Colors: green = healthy, amber = elevated errors, red = pain point (high p95 or error rate). Edge labels show call count, p95 latency, and error rate.
      </div>
    </div>
  )
}

ServiceGraph.propTypes = {
  traces: PropTypes.arrayOf(PropTypes.object).isRequired,
}
