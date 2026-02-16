import { useState, useEffect, useCallback } from 'react'
import { useAutoRefresh } from '../hooks'
import PageHeader from '../components/ui/PageHeader'
import AutoRefreshControl from '../components/ui/AutoRefreshControl'
import { queryLogs, getLabels, getLabelValues, getLogVolume } from '../api'
import { Card, Button, Alert } from '../components/ui'
import LogQueryForm from '../components/loki/LogQueryForm'
import LogResults from '../components/loki/LogResults'
import LogVolume from '../components/loki/LogVolume'
import LogQuickFilters from '../components/loki/LogQuickFilters'
import LogLabels from '../components/loki/LogLabels'
import { formatNsToIso } from '../utils/formatters'
import { LOKI_REFRESH_INTERVALS } from '../utils/constants'
import { useToast } from '../contexts/ToastContext'
import HelpTooltip from '../components/HelpTooltip'
import {
  normalizeLabelValues,
  computeTopTermsFromResult,
  getVolumeValues,
  buildFallbackVolume,
  buildSelectorFromFilters,
  escapeLogQLValue,
} from '../utils/lokiQueryUtils'

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

  const toast = useToast()

  // use shared hook for auto-refresh (keeps behavior identical but removes manual timers)
  useAutoRefresh(() => executeQuery(), refreshInterval * 1000, autoRefresh)

  const loadInitialData = useCallback(async () => {
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
  }, [])

  useEffect(() => { loadInitialData() }, [loadInitialData])

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
      <PageHeader icon="view_stream" title="Logs" subtitle="Query and analyze logs using LogQL">
        <AutoRefreshControl
          enabled={autoRefresh}
          onToggle={setAutoRefresh}
          interval={refreshInterval}
          onIntervalChange={setRefreshInterval}
          intervalOptions={LOKI_REFRESH_INTERVALS}
        />
      </PageHeader>

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
          <LogVolume volume={volume} />
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
