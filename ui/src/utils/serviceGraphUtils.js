import dagre from '@dagrejs/dagre'
import { Position, MarkerType } from 'reactflow'
import { getServiceName, getSpanAttribute, percentile, hasSpanError as spanHasErrorUtil } from './helpers'
import { formatDuration } from './formatters'

export const PAIN_P95_THRESHOLD_US = 1_000_000
export const WARN_P95_THRESHOLD_US = 300_000

function findParentSpanById(spans, parentId) {
  return spans.find((span) => (span.spanId || span.spanID) === parentId)
}

function findRootSpan(spans) {
  return spans.find((span) => !(span.parentSpanId || span.parentSpanID)) || spans[0]
}

export function buildServiceGraphData(traces) {
  const services = new Map()
  const edges = new Map()
  const traceEdges = []

  const addEdge = (source, target, duration = 0, hasError = false, count = 1) => {
    if (!source || !target || source === target) return
    const key = `${source}->${target}`
    const edge = edges.get(key) || { count: 0, durations: [], errors: 0 }
    edge.count += count
    if (duration > 0) edge.durations.push(duration)
    if (hasError) edge.errors += 1
    edges.set(key, edge)
  }

  traces.forEach((trace) => {
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

    spans.forEach((span) => {
      const serviceName = getServiceName(span)
      if (!services.has(serviceName)) {
        services.set(serviceName, { spans: 0, errors: 0, durations: [], traces: new Set(), inbound: 0, outbound: 0 })
      }
      const stats = services.get(serviceName)
      stats.spans += 1
      stats.traces.add(trace.traceID || trace.traceId || '')
      const duration = Number(span.duration || 0)
      if (duration > 0) stats.durations.push(duration)
      const hasError = spanHasErrorUtil(span)
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
        'server.name',
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
      const servicesInTrace = new Set(spans.map((span) => getServiceName(span)).filter(Boolean))
      servicesInTrace.delete(rootService)
      servicesInTrace.forEach((service) => {
        addLocalEdge(rootService, service, 0, false, 1)
      })
    }

    for (const [key, val] of localEdges.entries()) {
      const [src, dst] = key.split('->')
      // Global aggregation for stats
      addEdge(src, dst, 0, false, 0)
      const edge = edges.get(key)
      edge.count += val.count
      edge.durations.push(...val.durations)
      edge.errors += val.errors
      edges.set(key, edge)

      // Keep per-trace edge entries so we can render separate trace-level
      // connections instead of collapsing all traces into a single line.
      traceEdges.push({ key, source: src, target: dst, count: val.count, durations: val.durations.slice(), errors: val.errors, traceId: trace.traceID || trace.traceId })
    }
  })

  for (const [key, val] of edges.entries()) {
    const [src, dst] = key.split('->')
    if (services.has(src)) services.get(src).outbound += val.count
    if (services.has(dst)) services.get(dst).inbound += val.count
  }

  // Mark start/end services: a start has zero inbound, an end has zero outbound.
  for (const [name, stats] of services.entries()) {
    stats.isStart = stats.inbound === 0
    stats.isEnd = stats.outbound === 0
  }

  return { services, edges, traceEdges }
}

export function buildServiceGraphNodes(graphData, activeNodeId, hoverNodeId) {
  const nodes = []
  const entries = Array.from(graphData.services.entries()).sort((a, b) => a[0].localeCompare(b[0]))

  entries.forEach(([name, stats]) => {
    const p50 = percentile(stats.durations, 0.5)
    const p95 = percentile(stats.durations, 0.95)
    const errorRateNum = stats.spans ? (stats.errors / stats.spans) * 100 : 0
    const pain = p95 > PAIN_P95_THRESHOLD_US || errorRateNum > 5
    const colorClass = pain
      ? 'ring-2 ring-red-500/60'
      : p95 > WARN_P95_THRESHOLD_US || errorRateNum > 1
        ? 'ring-2 ring-yellow-400/60'
        : 'ring-2 ring-green-500/40'

    const isActive = activeNodeId === name || hoverNodeId === name
    const isConnected = activeNodeId
      ? graphData.edges.has(`${name}->${activeNodeId}`) || graphData.edges.has(`${activeNodeId}->${name}`)
      : true

    nodes.push({
      id: name,
      type: 'service',
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      position: { x: 0, y: 0 },
      className: isActive ? 'service-node-active' : '',
      style: {
        opacity: activeNodeId && !isConnected && !isActive ? 0.35 : 1,
        transition: 'opacity 200ms ease',
      },
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
          pain,
        },
      },
    })
  })

  return nodes
}

export function buildServiceGraphInsights(graphData) {
  const serviceStats = Array.from(graphData.services.entries()).map(([name, stats]) => {
    const p95 = percentile(stats.durations, 0.95)
    const errorRateNum = stats.spans ? (stats.errors / stats.spans) * 100 : 0
    return {
      name,
      p95,
      errorRateNum,
      spans: stats.spans,
      traces: stats.traces.size,
      inbound: stats.inbound,
      outbound: stats.outbound,
    }
  })

  const edgeStats = Array.from(graphData.edges.entries()).map(([key, val]) => {
    const [source, target] = key.split('->')
    const p95 = percentile(val.durations, 0.95)
    const errorRateNum = val.count ? (val.errors / val.count) * 100 : 0
    return {
      id: key,
      source,
      target,
      p95,
      errorRateNum,
      count: val.count,
    }
  })

  const painServices = serviceStats
    .filter((service) => service.p95 > PAIN_P95_THRESHOLD_US || service.errorRateNum > 5)
    .sort((a, b) => (b.p95 + b.errorRateNum) - (a.p95 + a.errorRateNum))
    .slice(0, 3)

  const topCalls = [...edgeStats].sort((a, b) => b.count - a.count).slice(0, 3)
  const topErrors = [...edgeStats].sort((a, b) => b.errorRateNum - a.errorRateNum).slice(0, 3)

  return { serviceStats, edgeStats, painServices, topCalls, topErrors }
}

export function buildServiceGraphEdges(graphData, activeEdgeId, activeNodeId) {
  // If per-trace edges are present, emit one edge per trace to visually
  // separate connections originating from different traces.
  if (graphData.traceEdges && graphData.traceEdges.length) {
    return graphData.traceEdges.map((te, idx) => {
      const { source, target, count, durations, errors, traceId } = te
      const p95 = percentile(durations, 0.95)
      const errorRateNum = count ? (errors / Math.max(1, count)) * 100 : 0
      const isPain = p95 > PAIN_P95_THRESHOLD_US || errorRateNum > 5
      const id = `${te.key}:${traceId}`
      const isActive = activeEdgeId === id
      const isConnectedToActive = activeNodeId ? source === activeNodeId || target === activeNodeId : true
      const fade = activeNodeId && !isConnectedToActive && !isActive

      // Use a small variety of dash patterns to visually separate parallel edges.
      const dashPatterns = ['0', '4 2', '6 3', '2 2']
      const dash = dashPatterns[idx % dashPatterns.length]

      const color = isPain
        ? '#ef4444'
        : p95 > WARN_P95_THRESHOLD_US || errorRateNum > 1
          ? '#f59e0b'
          : '#10b981'

      return {
        id,
        source,
        target,
        label: `${count} calls · p95 ${formatDuration(p95)} · err ${errorRateNum.toFixed(1)}% · ${traceId?.substring?.(0,8) || ''}`,
        animated: true,
        type: 'smoothstep',
        className: isActive ? 'edge-active' : '',
        style: {
          stroke: color,
          strokeWidth: isActive ? 3.5 : isPain ? 2.5 : 1.8,
          strokeDasharray: dash,
          opacity: fade ? 0.25 : 0.95,
        },
        labelStyle: {
          fontSize: 10,
          fontWeight: '500',
          fill: fade ? 'var(--sre-text-muted)' : 'var(--sre-text)',
        },
        labelBgStyle: {
          fill: 'var(--sre-surface)',
          fillOpacity: fade ? 0.4 : 0.9,
          stroke: 'var(--sre-border)',
          strokeWidth: 1,
          rx: 4,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color,
          width: isActive ? 18 : isPain ? 16 : 12,
          height: isActive ? 18 : isPain ? 16 : 12,
        },
      }
    })
  }

  return Array.from(graphData.edges.entries()).map(([key, val]) => {
    const [source, target] = key.split('->')
    const p95 = percentile(val.durations, 0.95)
    const errorRateNum = val.count ? (val.errors / val.count) * 100 : 0
    const isPain = p95 > PAIN_P95_THRESHOLD_US || errorRateNum > 5
    const isActive = activeEdgeId === key
    const isConnectedToActive = activeNodeId ? source === activeNodeId || target === activeNodeId : true
    const fade = activeNodeId && !isConnectedToActive && !isActive

    const color = isPain
      ? '#ef4444'
      : p95 > WARN_P95_THRESHOLD_US || errorRateNum > 1
        ? '#f59e0b'
        : '#10b981'

    return {
      id: key,
      source,
      target,
      label: `${val.count} calls · p95 ${formatDuration(p95)} · err ${errorRateNum.toFixed(1)}%`,
      animated: true,
      type: 'smoothstep',
      className: isActive ? 'edge-active' : '',
      style: {
        stroke: color,
        strokeWidth: isActive ? 4 : isPain ? 3 : 2,
        strokeDasharray: isActive ? '6 6' : isPain ? '4 4' : '0',
        opacity: fade ? 0.2 : 1,
        filter: isActive
          ? 'drop-shadow(0 0 6px rgba(59, 130, 246, 0.6))'
          : isPain
            ? 'drop-shadow(0 0 4px rgba(239, 68, 68, 0.5))'
            : 'none',
      },
      labelStyle: {
        fontSize: 11,
        fontWeight: '500',
        fill: fade ? 'var(--sre-text-muted)' : 'var(--sre-text)',
        filter: 'drop-shadow(0 0 2px var(--sre-bg))',
      },
      labelBgStyle: {
        fill: 'var(--sre-surface)',
        fillOpacity: fade ? 0.4 : 0.9,
        stroke: 'var(--sre-border)',
        strokeWidth: 1,
        rx: 4,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color,
        width: isActive ? 22 : isPain ? 20 : 16,
        height: isActive ? 22 : isPain ? 20 : 16,
      },
    }
  })
}

export function layoutServiceGraph(nodes, edges) {
  const nodeWidth = 260
  const nodeHeight = 140

  const graph = new dagre.graphlib.Graph()
  graph.setDefaultEdgeLabel(() => ({}))
  graph.setGraph({
    rankdir: 'LR',
    ranker: 'tight-tree',
    nodesep: 80,
    ranksep: 140,
    edgesep: 20,
    marginx: 20,
    marginy: 20,
  })

  nodes.forEach((node) => {
    graph.setNode(node.id, { width: nodeWidth, height: nodeHeight })
  })

  edges.forEach((edge) => {
    if (edge.source && edge.target) graph.setEdge(edge.source, edge.target)
  })

  dagre.layout(graph)

  // Detect connected components so we can vertically separate disconnected
  // subgraphs and avoid nodes collapsing into a single horizontal line.
  const adj = new Map()
  nodes.forEach((n) => adj.set(n.id, new Set()))
  edges.forEach((e) => {
    if (e.source && e.target && adj.has(e.source) && adj.has(e.target)) {
      adj.get(e.source).add(e.target)
      adj.get(e.target).add(e.source)
    }
  })

  const components = []
  const visited = new Set()
  for (const id of adj.keys()) {
    if (visited.has(id)) continue
    const stack = [id]
    const comp = []
    while (stack.length) {
      const cur = stack.pop()
      if (visited.has(cur)) continue
      visited.add(cur)
      comp.push(cur)
      for (const nb of adj.get(cur) || []) if (!visited.has(nb)) stack.push(nb)
    }
    components.push(comp)
  }

  // Compute layouted nodes from dagre and then offset each component vertically
  // so disconnected services are shown on separate rows.
  const nodePosMap = new Map()
  nodes.forEach((node) => {
    const pos = graph.node(node.id) || { x: 0, y: 0 }
    nodePosMap.set(node.id, { x: pos.x - nodeWidth / 2, y: pos.y - nodeHeight / 2 })
  })

  const compOffsets = new Map()
  const verticalGap = Math.max(80, graph.graph().ranksep || 140)
  components.forEach((comp, idx) => {
    // Compute min Y for the component
    let minY = Infinity
    comp.forEach((nid) => {
      const p = nodePosMap.get(nid)
      if (p && p.y < minY) minY = p.y
    })
    if (minY === Infinity) minY = 0
    const desiredTop = idx * (nodeHeight + verticalGap)
    const offset = desiredTop - minY
    compOffsets.set(idx, offset)
  })

  // Map node id -> component index
  const nodeToComp = new Map()
  components.forEach((comp, idx) => comp.forEach((nid) => nodeToComp.set(nid, idx)))

  const layoutedNodes = nodes.map((node) => {
    const base = nodePosMap.get(node.id) || { x: 0, y: 0 }
    const compIdx = nodeToComp.get(node.id) || 0
    const offset = compOffsets.get(compIdx) || 0
    return {
      ...node,
      position: { x: base.x, y: base.y + offset },
      style: { width: nodeWidth, height: nodeHeight },
    }
  })

  return { nodes: layoutedNodes, edges }
}