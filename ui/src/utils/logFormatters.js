export function formatNsToIso(ns) {
  if (!ns) return ''
  const ms = Math.round(Number(ns) / 1e6)
  return new Date(ms).toISOString()
}

export function formatRelativeTime(ns) {
  if (!ns) return ''
  const ms = Math.round(Number(ns) / 1e6)
  const now = Date.now()
  const diffMs = now - ms
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHr = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHr / 24)

  if (diffDay > 0) return `${diffDay}d ago`
  if (diffHr > 0) return `${diffHr}h ago`
  if (diffMin > 0) return `${diffMin}m ago`
  return `${diffSec}s ago`
}

export function formatLogLine(line) {
  try {
    const parsed = JSON.parse(line)
    return { type: 'json', data: parsed }
  } catch {
    return { type: 'text', data: line }
  }
}

export function getLogLevelColor(line) {
  const lowerLine = (typeof line === 'string' ? line : JSON.stringify(line)).toLowerCase()
  if (lowerLine.includes('error') || lowerLine.includes('fatal')) return 'text-red-400'
  if (lowerLine.includes('warn')) return 'text-yellow-400'
  if (lowerLine.includes('info')) return 'text-blue-400'
  if (lowerLine.includes('debug')) return 'text-gray-400'
  return 'text-sre-text'
}

export function getLogLevelBadge(line) {
  const lowerLine = (typeof line === 'string' ? line : JSON.stringify(line)).toLowerCase()
  if (lowerLine.includes('error') || lowerLine.includes('fatal')) return { text: 'ERROR', class: 'bg-red-500/20 text-red-400 border-red-500/30' }
  if (lowerLine.includes('warn')) return { text: 'WARN', class: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' }
  if (lowerLine.includes('info')) return { text: 'INFO', class: 'bg-blue-500/20 text-blue-400 border-blue-500/30' }
  if (lowerLine.includes('debug')) return { text: 'DEBUG', class: 'bg-gray-500/20 text-gray-400 border-gray-500/30' }
  return { text: 'LOG', class: 'bg-sre-surface text-sre-text-muted border-sre-border' }
}
