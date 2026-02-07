/**
 * General helper utilities
 */

/**
 * Get log level information from log line
 * @param {string|object} line - Log line to analyze
 * @returns {{text: string, color: string, bgClass: string}} Log level info
*/

export function getLogLevel(line) {
  const lowerLine = (typeof line === 'string' ? line : JSON.stringify(line)).toLowerCase()
  
  if (lowerLine.includes('error') || lowerLine.includes('fatal')) {
    return { text: 'ERROR', color: 'text-red-400', bgClass: 'bg-red-500/20 text-red-400 border-red-500/30' }
  }
  if (lowerLine.includes('warn')) {
    return { text: 'WARN', color: 'text-yellow-400', bgClass: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' }
  }
  if (lowerLine.includes('info')) {
    return { text: 'INFO', color: 'text-blue-400', bgClass: 'bg-blue-500/20 text-blue-400 border-blue-500/30' }
  }
  if (lowerLine.includes('debug')) {
    return { text: 'DEBUG', color: 'text-gray-400', bgClass: 'bg-gray-500/20 text-gray-400 border-gray-500/30' }
  }
  
  return { text: 'LOG', color: 'text-sre-text', bgClass: 'bg-sre-surface text-sre-text-muted border-sre-border' }
}

/**
 * Extract service name from span
 * @param {object} span - Span object
 * @returns {string} Service name
*/

export function getServiceName(span) {
  if (!span) return 'unknown'
  if (span.serviceName) return span.serviceName
  if (span.process?.serviceName) return span.process.serviceName
  
  if (Array.isArray(span.tags)) {
    const t = span.tags.find(t => 
      t.key === 'service.name' || 
      t.key === 'service' || 
      t.key?.toLowerCase().includes('service')
    )
    if (t && (t.value || t.value === 0)) return String(t.value)
  } else if (span.tags && typeof span.tags === 'object') {
    if (span.tags['service.name']) return String(span.tags['service.name'])
    if (span.tags['service']) return String(span.tags['service'])
    const k = Object.keys(span.tags).find(k => k.toLowerCase().includes('service'))
    if (k) return String(span.tags[k])
  }
  
  if (span.attributes && typeof span.attributes === 'object') {
    if (span.attributes['service.name']) return String(span.attributes['service.name'])
    if (span.attributes['service']) return String(span.attributes['service'])
  }
  
  return 'unknown'
}

/**
 * Get span attribute value
 * @param {object} span - Span object
 * @param {string|string[]} keys - Attribute key(s) to look for
 * @returns {any} Attribute value or null
 */
export function getSpanAttribute(span, keys) {
  if (!span) return null
  const keyList = Array.isArray(keys) ? keys : [keys]

  if (span.attributes && typeof span.attributes === 'object') {
    for (const k of keyList) {
      if (span.attributes[k] !== undefined && span.attributes[k] !== null) {
        return span.attributes[k]
      }
    }
  }

  if (Array.isArray(span.tags)) {
    for (const k of keyList) {
      const t = span.tags.find(tag => tag?.key === k)
      if (t?.value != null) return t.value
    }
  } else if (span.tags && typeof span.tags === 'object') {
    for (const k of keyList) {
      if (span.tags[k] !== undefined && span.tags[k] !== null) return span.tags[k]
    }
  }

  return null
}

/**
 * Calculate percentile of an array
 * @param {number[]} arr - Array of numbers
 * @param {number} p - Percentile (0-1)
 * @returns {number} Percentile value
 */
export function percentile(arr, p) {
  if (!arr.length) return 0
  const sorted = [...arr].sort((a, b) => a - b)
  const idx = Math.min(sorted.length - 1, Math.max(0, Math.floor(sorted.length * p)))
  return sorted[idx]
}

/**
 * Copy text to clipboard
 * @param {string} text - Text to copy
 * @returns {Promise<void>}
 */
export async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch (err) {
    console.error('Failed to copy:', err)
    return false
  }
}

/**
 * Download data as JSON file
 * @param {any} data - Data to download
 * @param {string} filename - File name
 */
export function downloadJSON(data, filename = 'data.json') {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/**
 * Debounce function
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in ms
 * @returns {Function} Debounced function
 */
export function debounce(func, wait) {
  let timeout
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout)
      func(...args)
    }
    clearTimeout(timeout)
    timeout = setTimeout(later, wait)
  }
}

/**
 * Deep clone an object
 * @param {any} obj - Object to clone
 * @returns {any} Cloned object
 */
export function deepClone(obj) {
  try {
    return JSON.parse(JSON.stringify(obj))
  } catch {
    return obj
  }
}

/**
 * Check if value is empty
 * @param {any} value - Value to check
 * @returns {boolean} True if empty
 */
export function isEmpty(value) {
  if (value === null || value === undefined) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  if (typeof value === 'object') return Object.keys(value).length === 0
  return false
}

/**
 * Generate unique ID
 * @returns {string} Unique ID
 */
export function generateId() {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
}
