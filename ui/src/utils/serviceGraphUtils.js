`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

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
      addEdge(src, dst, 0, false, 0)
      const edge = edges.get(key)
      edge.count += val.count
      edge.durations.push(...val.durations)
      edge.errors += val.errors
      edges.set(key, edge)
    }
  })

  for (const [key, val] of edges.entries()) {
    const [src, dst] = key.split('->')
    if (services.has(src)) services.get(src).outbound += val.count
    if (services.has(dst)) services.get(dst).inbound += val.count
  }

  return { services, edges }
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

  const layoutedNodes = nodes.map((node) => {
    const pos = graph.node(node.id)
    return {
      ...node,
      position: { x: pos.x - nodeWidth / 2, y: pos.y - nodeHeight / 2 },
      style: { width: nodeWidth, height: nodeHeight },
    }
  })

  return { nodes: layoutedNodes, edges }
}