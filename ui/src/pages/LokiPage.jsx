import { useState, useEffect, useRef, useCallback } from 'react'
import { queryLogs, getLabels, getLabelValues, getLogVolume } from '../api'
import { Card, Button, Alert } from '../components/ui'
import LogQueryForm from '../components/loki/LogQueryForm'
import LogResults from '../components/loki/LogResults'
import LogVolume from '../components/loki/LogVolume'
import LogQuickFilters from '../components/loki/LogQuickFilters'
import LogLabels from '../components/loki/LogLabels'
import { formatNsToIso } from '../utils/formatters'
import { useToast } from '../contexts/ToastContext'
import HelpTooltip from '../components/HelpTooltip'

function escapeLogQLValue(value) {
  const s = String(value)
  return JSON.stringify(s).slice(1, -1)
}

function normalizeLabelValue(label, value) {
  if (value === null || value === undefined) return ''
  const raw = String(value).trim()
  if (!raw) return ''
  const escapedLabel = String(label).replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\\$&`)
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

function normalizeLabelValues(label, values) {
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

function normalizeToken(tok) {
  return tok.replaceAll(/(?:^\W+|\W+$)/g, '')
}

function isTokenValid(tok, stopwords) {
  if (tok.length < 3) return false
  if (/^\d+$/.test(tok)) return false
  if (stopwords.has(tok)) return false
  return true
}

function collectTokensFromValues(values, stopwords, maxSamples, state, tokens) {
  for (const v of values) {
    if (state.seen++ > maxSamples) {
      state.done = true
      return
    }
    const parts = getLogText(v[1]).toLowerCase().split(/[^a-z0-9_+-]+/).filter(Boolean)
    const cleaned = parts
      .filter(tok => isTokenValid(tok, stopwords))
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
        .filter(tok => isTokenValid(tok, stopwords))
        .map(normalizeToken)
        .filter(Boolean)
      tokens.push(...cleaned)
    }
  }
  return tokens
}

function countTokens(tokens) {
  return tokens.reduce((acc, t) => {
    acc[t] = (acc[t] || 0) + 1
    return acc
  }, {})
}

function mapTopTerms(freq, maxTerms) {
  const arr = Object.entries(freq).map(([term, count]) => ({ term, count })).sort((a, b) => b.count - a.count)
  return arr.slice(0, maxTerms).map(item => {
    let icon = 'search'
    let iconClass = ''
    if (item.term.includes('error')) { icon = 'error'; iconClass = 'text-red-500' }
    else if (item.term.includes('warn')) { icon = 'warning'; iconClass = 'text-yellow-500' }
    else if (item.term.includes('timeout') || item.term.includes('timedout')) { icon = 'schedule'; iconClass = 'text-orange-500' }
    else if (item.term.includes('exception')) { icon = 'error_outline'; iconClass = 'text-red-400' }
    return { ...item, icon, iconClass }
  })
}

function computeTopTermsFromResult(res, maxTerms = 8) {
  if (!res?.data?.result) return []
  const stopwords = new Set(['the', 'and', 'for', 'with', 'that', 'this', 'from', 'are', 'was', 'but', 'not', 'you', 'your', 'have', 'has', 'will', 'can', 'http', 'https', 'info', 'message'])
  const tokens = collectTokensFromResults(res.data.result, 2000, stopwords)
  if (tokens.length === 0) {
    const fallbackTokens = collectTokensFromStreamLabels(res.data.result, stopwords)
    if (fallbackTokens.length === 0) return []
    return mapTopTerms(countTokens(fallbackTokens), maxTerms)
  }
  return mapTopTerms(countTokens(tokens), maxTerms)
}

function getVolumeValues(volRes) {
  return (volRes?.data?.result?.[0]?.values || []).map(v => Number(v[1]))
}

function buildLabelMatcher(label, value) {
  if (value === '__any__') return `${label}=~".+"`
  return `${label}="${escapeLogQLValue(value)}"`
}

function buildFallbackVolume(res, totalLogs) {
  const buckets = {}
  if (res?.data?.result) {
    for (const stream of res.data.result) {
      for (const [ts] of (stream.values || [])) {
        const bucket = Math.floor(Number.parseInt(ts, 10) / 1e9 / 60)
        buckets[bucket] = (buckets[bucket] || 0) + 1
      }
    }
  }
  const volumeData = Object.values(buckets).slice(-60)
  if (volumeData?.length > 0) return volumeData
  if (totalLogs > 0) return new Array(10).fill(Math.ceil(totalLogs / 10))
  return [0]
}

/**
 * Build a LogQL selector from an array of filter objects
 */
function buildSelectorFromFilters(filters, fallbackLabel = 'service_name') {
  if (!filters?.length) {
    return `{${fallbackLabel}=~".+"}`
  }
  const parts = filters.map(f => buildLabelMatcher(f.label, f.value))
  return `{${parts.join(',')}}`
}

export default function LokiPage() {
  const [labels, setLabels] = useState([])
  const [labelValuesCache, setLabelValuesCache] = useState({})
  const [loadingValues, setLoadingValues] = useState({})
  const [selectedFilters, setSelectedFilters] = useState([])
  const [selectedLabel, setSelectedLabel] = useState('')
  const [selectedValue, setSelectedValue] = useState('')
  const [pattern, setPattern] = useState('')
  const [rangeMinutes, setRangeMinutes] = useState(60)
  const [maxLogs, setMaxLogs] = useState(100)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [refreshInterval, setRefreshInterval] = useState(30)
  const [viewMode, setViewMode] = useState('table')
  const [expandedLogs, setExpandedLogs] = useState({})
  const [searchText, setSearchText] = useState('')
  const [queryMode, setQueryMode] = useState('builder')
  const [customLogQL, setCustomLogQL] = useState('')

  const [queryResult, setQueryResult] = useState(null)
  const [volume, setVolume] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [topTerms, setTopTerms] = useState([])
  const autoRefreshRef = useRef(null)

  const toast = useToast()

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadInitialData() }, [])

  useEffect(() => {
    if (autoRefresh) {
      autoRefreshRef.current = setInterval(() => {
        executeQuery()
      }, refreshInterval * 1000)
    } else if (autoRefreshRef.current) {
      clearInterval(autoRefreshRef.current)
      autoRefreshRef.current = null
    }
    return () => {
      if (autoRefreshRef.current) clearInterval(autoRefreshRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, refreshInterval, selectedFilters, pattern, rangeMinutes])

  async function loadInitialData() {
    try {
      const lbls = await getLabels()
      const labelsArray = (lbls?.data || []).filter((label) => typeof label === 'string' && label.trim() !== '')
      setLabels(labelsArray)

      if (labelsArray?.length > 0) {
        for (const label of labelsArray) {
          try {
            const vals = await getLabelValues(label)
            const normalizedValues = normalizeLabelValues(label, vals?.data || [])
            setLabelValuesCache(prev => ({ ...prev, [label]: normalizedValues }))
          } catch {
            // Silently skip labels that fail to load values
          }
        }
      }
    } catch {
      setLabels([])
    }
  }

  async function loadLabelValues(label) {
    if (!label || labelValuesCache[label]) return

    setLoadingValues(prev => ({ ...prev, [label]: true }))
    try {
      const end = Date.now() * 1e6
      const start = (Date.now() - rangeMinutes * 60 * 1000) * 1e6
      const vals = await getLabelValues(label, { start: Math.round(start), end: Math.round(end) })
      const normalizedValues = normalizeLabelValues(label, vals?.data || [])
      setLabelValuesCache(prev => ({ ...prev, [label]: normalizedValues }))
    } catch {
      // Silently handle - label will remain un-cached
    } finally {
      setLoadingValues(prev => ({ ...prev, [label]: false }))
    }
  }

  function addFilter() {
    if (!selectedLabel || !selectedValue) return
    setSelectedFilters(prev => {
      const exists = prev.find(p => p.label === selectedLabel && p.value === selectedValue)
      if (exists) return prev
      return [...prev, { label: selectedLabel, value: selectedValue }]
    })
    setSelectedLabel('')
    setSelectedValue('')
  }

  function removeFilter(i) {
    setSelectedFilters(prev => prev.filter((_, idx) => idx !== i))
  }

  function clearAllFilters() {
    setSelectedFilters([])
    setPattern('')
  }

  function getEffectiveFilters(overrideFilters) {
    if (overrideFilters) return overrideFilters
    if (selectedFilters.length) return selectedFilters
    if (selectedLabel && selectedValue) return [{ label: selectedLabel, value: selectedValue }]
    return []
  }

  function toggleLogExpand(logKey) {
    setExpandedLogs(prev => ({ ...prev, [logKey]: !prev[logKey] }))
  }

  function downloadLogs() {
    if (!queryResult?.data?.result) return
    const logs = []
    queryResult.data.result.forEach(stream => {
      stream.values.forEach(v => {
        logs.push({
          timestamp: formatNsToIso(v[0]),
          stream: stream.stream,
          log: v[1]
        })
      })
    })
    const blob = new Blob([JSON.stringify(logs, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `loki-logs-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  function filterDisplayedLogs(stream) {
    if (!stream?.values) return []
    if (!searchText) return stream.values
    const tokens = String(searchText).toLowerCase().split(/\s+/).filter(Boolean)
    return stream.values.filter(v => {
      const logText = typeof v[1] === 'string' ? v[1] : JSON.stringify(v[1])
      const labelsText = stream.stream ? Object.values(stream.stream).join(' ') : ''
      const hay = (logText + ' ' + labelsText).toLowerCase()
      return tokens.every(t => hay.includes(t))
    })
  }

  async function fetchAndSetVolume(volumeQuery, startNs, endNs, totalLogs, res) {
    try {
      const volRes = await getLogVolume(volumeQuery, { start: Math.round(startNs), end: Math.round(endNs), step: Math.max(60, Math.floor(rangeMinutes * 60 / 60)) })
      const vals = getVolumeValues(volRes)
      if (vals.some(v => v > 0)) {
        setVolume(vals)
        return
      }
    } catch {
      // Fall back to computed volume
    }
    setVolume(buildFallbackVolume(res, totalLogs))
  }

  /**
   * Core query executor — used by all query paths (form submit, quick filters, auto-refresh)
   */
  async function executeQuery(overrideFilters, overridePattern) {
    setError(null)
    setLoading(true)

    const effectivePattern = overridePattern !== undefined ? overridePattern : pattern
    const fallbackLabel = labels[0] || 'service_name'

    try {
      let q
      let selectorForVolume

      if (queryMode === 'custom' && overrideFilters === undefined) {
        q = customLogQL.trim()
        if (!q) {
          setError('Please enter a LogQL query')
          setLoading(false)
          return
        }
        selectorForVolume = q
      } else {
        const filters = getEffectiveFilters(overrideFilters)
        const selector = buildSelectorFromFilters(filters, fallbackLabel)
        selectorForVolume = selector
        q = selector
        if (effectivePattern) {
          const escaped = escapeLogQLValue(effectivePattern)
          q += ` |= "${escaped}"`
          selectorForVolume = `${selector} |= "${escaped}"`
        }
      }

      const start = Date.now() - rangeMinutes * 60 * 1000
      const startNs = start * 1e6
      const endNs = Date.now() * 1e6

      const res = await queryLogs({ query: q, start: Math.round(startNs), end: Math.round(endNs), limit: maxLogs })
      setQueryResult(res)

      try {
        setTopTerms(computeTopTermsFromResult(res, 12))
      } catch {
        setTopTerms([])
      }

      const totalLogs = res.data?.result?.reduce((acc, stream) => acc + (stream.values?.length || 0), 0) || 0
      await fetchAndSetVolume(selectorForVolume, startNs, endNs, totalLogs, res)
    } catch (e) {
      setError(e.message || 'Failed to query logs')
    } finally {
      setLoading(false)
    }
  }

  function runQuery(e) {
    e?.preventDefault?.()
    executeQuery()
  }

  function handleSelectLabelValue(label, value) {
    const filters = [{ label, value }]
    setSelectedFilters(filters)
    setPattern('')
    setQueryMode('builder')
    executeQuery(filters, '')
  }

  function handleSelectPattern(term) {
    setSelectedFilters([])
    setPattern(term)
    setQueryMode('builder')
    executeQuery([], term)
  }

  async function copyToClipboard(text) {
    const value = typeof text === 'string' ? text : JSON.stringify(text)
    try {
      await navigator.clipboard.writeText(value)
      toast.success('Copied to clipboard')
    } catch {
      toast.error('Failed to copy to clipboard')
    }
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-3xl font-bold text-sre-text mb-2">
              <span className="material-icons text-sre-primary text-3xl align-middle">view_stream</span>{' '}Logs
            </h1>
            <p className="text-sre-text-muted">Query and analyze logs using LogQL</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-sre-text">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-sre-border bg-sre-surface"
            />
            <span>Auto-refresh</span>
            <HelpTooltip text="Automatically refresh the query results at the selected interval. Useful for monitoring live logs." />
          </label>
          {autoRefresh && (
            <div className="flex items-center gap-2">
              <select value={refreshInterval} onChange={(e) => setRefreshInterval(Number(e.target.value))} className="px-2 pr-10 py-1 bg-sre-surface border border-sre-border rounded text-sm">
                <option value={10}>10s</option>
                <option value={30}>30s</option>
                <option value={60}>60s</option>
                <option value={300}>5m</option>
              </select>
              <HelpTooltip text="How often to automatically refresh the log query. Shorter intervals provide more real-time data but increase server load." />
            </div>
          )}
        </div>
      </div>

      {error && (
        <Alert variant="error" className="mb-6" onClose={() => setError(null)}>
          <strong>Error:</strong> {error}
        </Alert>
      )}

      <Card title="Search & Filter" className="mb-6">
        <LogQueryForm
          queryMode={queryMode}
          customLogQL={customLogQL}
          setCustomLogQL={setCustomLogQL}
          labels={labels}
          selectedLabel={selectedLabel}
          setSelectedLabel={setSelectedLabel}
          labelValuesCache={labelValuesCache}
          loadingValues={loadingValues}
          selectedValue={selectedValue}
          setSelectedValue={setSelectedValue}
          pattern={pattern}
          setPattern={setPattern}
          rangeMinutes={rangeMinutes}
          setRangeMinutes={setRangeMinutes}
          maxLogs={maxLogs}
          setMaxLogs={setMaxLogs}
          addFilter={addFilter}
          selectedFilters={selectedFilters}
          clearAllFilters={clearAllFilters}
          runQuery={runQuery}
          onQueryModeChange={(e) => setQueryMode(e.target.value)}
          onLabelChange={loadLabelValues}
          loading={loading}
          onRemoveFilter={removeFilter}
        />
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-3">
          <Card title="Log Results" subtitle={queryResult?.data?.result?.length ? 'Showing results' : 'Run a query'}>
            <div className="mb-4 flex items-center justify-between pb-4 border-b border-sre-border">
              <div className="flex items-center gap-4">
                <div className="flex gap-1 bg-sre-bg-alt rounded-lg p-1">
                  {['table', 'compact', 'raw'].map(mode => (
                    <button key={mode} onClick={() => setViewMode(mode)} className={`px-3 py-1 rounded text-xs font-medium transition-colors ${viewMode === mode ? 'bg-sre-primary text-white' : 'text-sre-text-muted hover:text-sre-text'}`}>
                      {mode.charAt(0).toUpperCase() + mode.slice(1)}
                    </button>
                  ))}
                </div>

                <input type="text" value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder="Filter displayed logs..." className="px-3 py-1 bg-sre-surface border border-sre-border rounded text-sm text-sre-text w-64" />
                <HelpTooltip text="Filter the displayed log results by searching within the log content. Supports multiple keywords separated by spaces." />
              </div>

              <div className="flex gap-2">
                <Button size="sm" variant="ghost" onClick={downloadLogs} disabled={!queryResult?.data?.result?.length}>
                  <span className="material-icons text-sm mr-1">download</span> Export
                </Button>
              </div>
            </div>

            <LogResults
              key={`log-results-${viewMode}`}
              queryResult={queryResult}
              loading={loading}
              filterDisplayedLogs={filterDisplayedLogs}
              searchText={searchText}
              viewMode={viewMode}
              expandedLogs={expandedLogs}
              toggleLogExpand={toggleLogExpand}
              copyToClipboard={copyToClipboard}
            />
          </Card>
        </div>

        <div className="space-y-6">
          {volume?.length > 0 && <LogVolume volume={volume} />}
          <LogQuickFilters
            labelValuesCache={labelValuesCache}
            topTerms={topTerms}
            onSelectLabelValue={handleSelectLabelValue}
            onSelectPattern={handleSelectPattern}
          />
          <LogLabels labels={labels} labelValuesCache={labelValuesCache} />
        </div>
      </div>
    </div>
  )
}
