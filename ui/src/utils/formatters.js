/**
 * Format nanoseconds to ISO string
 * @param {number|string} ns - Nanoseconds timestamp
 * @returns {string} ISO formatted date string
 */
export function formatNsToIso(ns) {
  if (!ns) return ''
  const ms = Math.round(Number(ns) / 1e6)
  return new Date(ms).toISOString()
}

/**
 * Format timestamp to relative time (e.g., "2h ago")
 * @param {number|string} ns - Nanoseconds timestamp
 * @returns {string} Relative time string
 */
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

/**
 * Format duration in nanoseconds to human-readable string
 * @param {number} ns - Duration in nanoseconds
 * @returns {string} Formatted duration (e.g., "150ms", "2.5s")
 */
export function formatDuration(ns) {
  if (ns === null || ns === undefined || Number.isNaN(ns)) return '0ms'
  const safe = Math.max(0, Number(ns))
  const ms = safe / 1000000

  if (ms < 1) return `${(safe / 1000).toFixed(0)}μs`
  if (ms < 1000) return `${ms.toFixed(2)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

/**
 * Format bytes to human-readable size
 * @param {number} bytes - Size in bytes
 * @param {number} decimals - Number of decimal places
 * @returns {string} Formatted size (e.g., "1.5 MB")
 */
export function formatBytes(bytes, decimals = 2) {
  if (bytes === 0) return '0 Bytes'
  
  const k = 1024
  const dm = Math.max(0, decimals)
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
  
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  
  return `${Number.parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`
}

/**
 * Format number with thousand separators
 * @param {number} num - Number to format
 * @returns {string} Formatted number (e.g., "1,234,567")
 */
export function formatNumber(num) {
  return new Intl.NumberFormat().format(num)
}

/**
 * Format percentage
 * @param {number} value - Value to format
 * @param {number} decimals - Number of decimal places
 * @returns {string} Formatted percentage (e.g., "45.67%")
 */
export function formatPercentage(value, decimals = 1) {
  return `${Number(value).toFixed(decimals)}%`
}

/**
 * Truncate string to specified length
 * @param {string} str - String to truncate
 * @param {number} length - Maximum length
 * @returns {string} Truncated string with ellipsis
 */
export function truncate(str, length = 50) {
  if (!str || str.length <= length) return str
  return `${str.substring(0, length)}...`
}

/**
 * Format JSON for display
 * @param {object} obj - Object to format
 * @param {number} indent - Indentation spaces
 * @returns {string} Formatted JSON string
 */
export function formatJSON(obj, indent = 2) {
  try {
    return JSON.stringify(obj, null, indent)
  } catch {
    return '[Invalid JSON]'
  }
}

/**
 * Parse log line (JSON or text)
 * @param {string} line - Log line to parse
 * @returns {{type: string, data: any}} Parsed log with type
 */
export function parseLogLine(line) {
  try {
    const parsed = JSON.parse(line)
    return { type: 'json', data: parsed }
  } catch {
    return { type: 'text', data: line }
  }
}
