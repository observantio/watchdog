function escapeRegexLiteral(value) {
  return String(value).replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\\$&`)
}

export function escapeLogQLValue(value) {
  const s = String(value)
  return JSON.stringify(s).slice(1, -1)
}

export function normalizeLabelValue(label, value) {
  if (value === null || value === undefined) return ''
  const raw = String(value).trim()
  if (!raw) return ''

  const escapedLabel = escapeRegexLiteral(label)
  const matcher = new RegExp(`${escapedLabel}="([^"]+)"`)
  const match = matcher.exec(raw)
  if (match?.[1]) return match[1]

  if (raw.includes('="') && !raw.startsWith(`${label}="`)) {
    const prefixed = `${label}="${raw}`
    const prefMatch = matcher.exec(prefixed)
    if (prefMatch?.[1]) return prefMatch[1]
  }

  const cutIndex = raw.indexOf('",')
  if (cutIndex > 0) return raw.slice(0, cutIndex)

  return raw
}

export function normalizeLabelValues(label, values) {
  const cleaned = (values || [])
    .map((value) => normalizeLabelValue(label, value))
    .filter(Boolean)
  return Array.from(new Set(cleaned)).sort((a, b) => a.localeCompare(b))
}

function getLogText(raw) {
  try {
    const parsed = JSON.parse(raw)
    return Object.values(parsed).join(' ')
  } catch {
    return String(raw)
  }
}

function normalizeToken(token) {
  return token.replaceAll(/(?:^\W+|\W+$)/g, '')
}

function isTokenValid(token, stopwords) {
  if (token.length < 3) return false
  if (/^\d+$/.test(token)) return false
  if (stopwords.has(token)) return false
  return true
}

function collectTokensFromValues(values, stopwords, maxSamples, state, tokens) {
  for (const value of values) {
    if (state.seen++ > maxSamples) {
      state.done = true
      return
    }
    const parts = getLogText(value[1]).toLowerCase().split(/[^a-z0-9_+-]+/).filter(Boolean)
    const cleaned = parts
      .filter((token) => isTokenValid(token, stopwords))
      .map(normalizeToken)
      .filter(Boolean)
    tokens.push(...cleaned)
  }
}

function collectTokensFromResults(result, maxSamples, stopwords) {
  if (!result) return []
  const tokens = []
  const state = { seen: 0, done: false }
  for (const stream of result) {
    collectTokensFromValues(stream.values || [], stopwords, maxSamples, state, tokens)
    if (state.done) break
  }
  return tokens
}

function collectTokensFromStreamLabels(result, stopwords) {
  if (!result) return []
  const tokens = []
  for (const stream of result) {
    const labels = stream.stream || {}
    for (const value of Object.values(labels)) {
      const parts = String(value).toLowerCase().split(/[^a-z0-9_+-]+/).filter(Boolean)
      const cleaned = parts
        .filter((token) => isTokenValid(token, stopwords))
        .map(normalizeToken)
        .filter(Boolean)
      tokens.push(...cleaned)
    }
  }
  return tokens
}

function countTokens(tokens) {
  return tokens.reduce((acc, token) => {
    acc[token] = (acc[token] || 0) + 1
    return acc
  }, {})
}

function mapTopTerms(freq, maxTerms) {
  const arr = Object.entries(freq)
    .map(([term, count]) => ({ term, count }))
    .sort((a, b) => b.count - a.count)

  return arr.slice(0, maxTerms).map((item) => {
    let icon = 'search'
    let iconClass = ''
    if (item.term.includes('error')) {
      icon = 'error'
      iconClass = 'text-red-500'
    } else if (item.term.includes('warn')) {
      icon = 'warning'
      iconClass = 'text-yellow-500'
    } else if (item.term.includes('timeout') || item.term.includes('timedout')) {
      icon = 'schedule'
      iconClass = 'text-orange-500'
    } else if (item.term.includes('exception')) {
      icon = 'error_outline'
      iconClass = 'text-red-400'
    }
    return { ...item, icon, iconClass }
  })
}

export function computeTopTermsFromResult(result, maxTerms = 8) {
  if (!result?.data?.result) return []

  const stopwords = new Set([
    'the', 'and', 'for', 'with', 'that', 'this', 'from', 'are', 'was', 'but', 'not',
    'you', 'your', 'have', 'has', 'will', 'can', 'http', 'https', 'info', 'message',
  ])

  const tokens = collectTokensFromResults(result.data.result, 2000, stopwords)
  if (tokens.length === 0) {
    const fallbackTokens = collectTokensFromStreamLabels(result.data.result, stopwords)
    if (fallbackTokens.length === 0) return []
    return mapTopTerms(countTokens(fallbackTokens), maxTerms)
  }

  return mapTopTerms(countTokens(tokens), maxTerms)
}

export function getVolumeValues(volumeResponse) {
  return (volumeResponse?.data?.result?.[0]?.values || []).map((entry) => Number(entry[1]))
}

function buildLabelMatcher(label, value) {
  if (value === '__any__') return `${label}=~".+"`
  return `${label}="${escapeLogQLValue(value)}"`
}

export function buildFallbackVolume(response, totalLogs) {
  const buckets = {}
  if (response?.data?.result) {
    for (const stream of response.data.result) {
      for (const [ts] of stream.values || []) {
        const bucket = Math.floor(Number.parseInt(ts, 10) / 1e9 / 60)
        buckets[bucket] = (buckets[bucket] || 0) + 1
      }
    }
  }

  const volumeData = Object.values(buckets).slice(-60)
  if (volumeData.length > 0) return volumeData
  if (totalLogs > 0) return new Array(10).fill(Math.ceil(totalLogs / 10))
  return [0]
}

export function buildSelectorFromFilters(filters, fallbackLabel = 'service_name') {
  if (!filters?.length) {
    return `{${fallbackLabel}=~".+"}`
  }
  const parts = filters.map((filter) => buildLabelMatcher(filter.label, filter.value))
  return `{${parts.join(',')}}`
}
