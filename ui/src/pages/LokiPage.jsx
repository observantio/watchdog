import { useState, useEffect, useRef } from 'react'
import { queryLogs, getLabels, getLabelValues, getLogVolume } from '../api'
import { Card, Button, Alert, Spinner, Badge, Sparkline } from '../components/ui'

function formatNsToIso(ns){
  if(!ns) return ''
  const ms = Math.round(Number(ns)/1e6)
  return new Date(ms).toISOString()
}

function formatRelativeTime(ns){
  if(!ns) return ''
  const ms = Math.round(Number(ns)/1e6)
  const now = Date.now()
  const diffMs = now - ms
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHr = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHr / 24)
  
  if(diffDay > 0) return `${diffDay}d ago`
  if(diffHr > 0) return `${diffHr}h ago`
  if(diffMin > 0) return `${diffMin}m ago`
  return `${diffSec}s ago`
}

function formatLogLine(line){
  try {
    const parsed = JSON.parse(line)
    return { type: 'json', data: parsed }
  } catch {
    return { type: 'text', data: line }
  }
}

function getLogLevelColor(line){
  const lowerLine = (typeof line === 'string' ? line : JSON.stringify(line)).toLowerCase()
  if (lowerLine.includes('error') || lowerLine.includes('fatal')) return 'text-red-400'
  if (lowerLine.includes('warn')) return 'text-yellow-400'
  if (lowerLine.includes('info')) return 'text-blue-400'
  if (lowerLine.includes('debug')) return 'text-gray-400'
  return 'text-sre-text'
}

function getLogLevelBadge(line){
  const lowerLine = (typeof line === 'string' ? line : JSON.stringify(line)).toLowerCase()
  if (lowerLine.includes('error') || lowerLine.includes('fatal')) return { text: 'ERROR', class: 'bg-red-500/20 text-red-400 border-red-500/30' }
  if (lowerLine.includes('warn')) return { text: 'WARN', class: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' }
  if (lowerLine.includes('info')) return { text: 'INFO', class: 'bg-blue-500/20 text-blue-400 border-blue-500/30' }
  if (lowerLine.includes('debug')) return { text: 'DEBUG', class: 'bg-gray-500/20 text-gray-400 border-gray-500/30' }
  return { text: 'LOG', class: 'bg-sre-surface text-sre-text-muted border-sre-border' }
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
  const [showTimeline, setShowTimeline] = useState(true)
  const [queryMode, setQueryMode] = useState('builder')
  const [customLogQL, setCustomLogQL] = useState('')
  
  const [queryResult, setQueryResult] = useState(null)
  const [volume, setVolume] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [lastQuery, setLastQuery] = useState('')
  const [topTerms, setTopTerms] = useState([])
  
  
  const autoRefreshRef = useRef(null)

  useEffect(()=>{
    loadInitialData()
  },[])
  
  useEffect(()=>{
    if(autoRefresh){
      autoRefreshRef.current = setInterval(()=>{
        runQuery()
      }, refreshInterval * 1000)
    } else {
      if(autoRefreshRef.current){
        clearInterval(autoRefreshRef.current)
        autoRefreshRef.current = null
      }
    }
    return () => {
      if(autoRefreshRef.current) clearInterval(autoRefreshRef.current)
    }
  }, [autoRefresh, refreshInterval, selectedFilters, pattern, rangeMinutes])
  
  async function loadInitialData(){
    try {
      const lbls = await getLabels()
      console.log('[LokiPage] getLabels response:', lbls)
      const labelsArray = lbls?.data || []
      console.log('[LokiPage] Setting labels:', labelsArray)
      setLabels(labelsArray)
      
      if(labelsArray.length > 0){
        for(const label of labelsArray){
          try {
            const vals = await getLabelValues(label)
            console.log(`[LokiPage] getLabelValues(${label}):`, vals)
            setLabelValuesCache(prev => ({...prev, [label]: vals?.data || []}))
          } catch(e) {
            console.warn(`Failed to load values for ${label}:`, e)
          }
        }
      }
    } catch(e) {
      console.error('[LokiPage] Failed to load labels:', e)
      setLabels([])
    }
  }

  async function loadLabelValues(label){
    if(!label) return
    if(labelValuesCache[label]) return
    
    setLoadingValues(prev => ({...prev, [label]: true}))
    try{
      const vals = await getLabelValues(label)
      setLabelValuesCache(prev => ({...prev, [label]: vals.data || []}))
    }catch(e){
      console.warn('Failed to load label values for', label, e)
    }finally{
      setLoadingValues(prev => ({...prev, [label]: false}))
    }
  }

  function addFilter(){
    if(!selectedLabel || !selectedValue) return
    setSelectedFilters(prev => {
      const exists = prev.find(p=>p.label===selectedLabel && p.value===selectedValue)
      if(exists) return prev
      return [...prev, {label:selectedLabel, value:selectedValue}]
    })
    setSelectedLabel('')
    setSelectedValue('')
  }

  function removeFilter(i){
    setSelectedFilters(prev => prev.filter((_,idx)=>idx!==i))
  }
  
  function clearAllFilters(){
    setSelectedFilters([])
    setPattern('')
  }

  function buildSelector(){
    if(!selectedFilters.length) {
      // Return a selector that matches all logs using the first available label
      const firstLabel = labels[0] || 'service_name'
      return `{${firstLabel}=~".+"}`
    }
    const parts = selectedFilters.map(f => (
      f.value === '__any__' ? `${f.label}=~".+"` : `${f.label}="${f.value}"`
    ))
    return `{${parts.join(',')}}`
  }
  
  function toggleLogExpand(logKey){
    setExpandedLogs(prev => ({...prev, [logKey]: !prev[logKey]}))
  }
  
  function copyToClipboard(text){
    navigator.clipboard.writeText(text).then(() => {
      alert('Copied to clipboard!')
    }).catch(err => {
      console.error('Failed to copy:', err)
    })
  }
  
  function downloadLogs(){
    if(!queryResult || !queryResult.data || !queryResult.data.result) return
    
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
    
    const blob = new Blob([JSON.stringify(logs, null, 2)], {type: 'application/json'})
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `loki-logs-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }
  
  function filterDisplayedLogs(logs){
    if(!searchText) return logs
    const search = searchText.toLowerCase()
    return logs.filter(v => {
      const logText = typeof v[1] === 'string' ? v[1] : JSON.stringify(v[1])
      return logText.toLowerCase().includes(search)
    })
  }

  function computeTopTermsFromResult(res, maxTerms = 8){
    try{
      if(!res || !res.data || !res.data.result) return []
      const stopwords = new Set(['the','and','for','with','that','this','from','are','was','but','not','you','your','have','has','will','can','http','https','info','message'])
      const freq = {}
      let seen = 0, maxSamples = 2000
      res.data.result.forEach(stream => {
        (stream.values || []).forEach(v => {
          if(seen++ > maxSamples) return
          const raw = v[1]
          let text = ''
          try{ const p = JSON.parse(raw); text = Object.values(p).join(' ') } catch(e){ text = String(raw) }
          text = text.toLowerCase()
          const tokens = text.split(/[^a-z0-9_+-]+/).filter(Boolean)
          tokens.forEach(tok => {
            if(tok.length < 3) return
            if(/^[0-9]+$/.test(tok)) return
            if(stopwords.has(tok)) return
            const t = tok.replace(/^\W+|\W+$/g, '')
            if(!t) return
            freq[t] = (freq[t] || 0) + 1
          })
        })
      })
      const arr = Object.entries(freq).map(([term,count]) => ({term, count})).sort((a,b)=>b.count - a.count)
      const top = arr.slice(0, maxTerms).map(item => {
        let icon = 'search', iconClass = ''
        if(item.term.includes('error')){ icon='error'; iconClass='text-red-500' }
        else if(item.term.includes('warn')){ icon='warning'; iconClass='text-yellow-500' }
        else if(item.term.includes('timeout') || item.term.includes('timedout')){ icon='schedule'; iconClass='text-orange-500' }
        else if(item.term.includes('exception')){ icon='error_outline'; iconClass='text-red-400' }
        return {...item, icon, iconClass}
      })
      return top
    }catch(e){
      console.warn('computeTopTermsFromResult error', e)
      return []
    }
  }

  async function runQuery(e){
    if(e && e.preventDefault) e.preventDefault()
    setError(null)
    setLoading(true)
    const queryStartTime = Date.now()
    
    try{
      let q
      if(queryMode === 'custom') {
        q = customLogQL.trim()
        if(!q) {
          setError('Please enter a LogQL query')
          setLoading(false)
          return
        }
      } else {
        const selector = buildSelector()
        q = selector
        if(pattern) q += ` |= "${pattern}"`
      }
      
      const start = Date.now() - rangeMinutes*60*1000
      const startNs = start * 1e6
      const endNs = Date.now() * 1e6
      
      console.log('[LokiPage] runQuery:', {query: q, start: Math.round(startNs), end: Math.round(endNs), limit: maxLogs})
      setLastQuery(q)

      const res = await queryLogs({query: q, start: Math.round(startNs), end: Math.round(endNs), limit: maxLogs})
      console.log('[LokiPage] queryLogs response:', res)
      setQueryResult(res)
      // update dynamic quick-search terms based on recent results
      try {
        const terms = computeTopTermsFromResult(res, 12)
        setTopTerms(terms)
      } catch (err) {
        console.warn('Failed to compute top terms:', err)
        setTopTerms([])
      }
      
      const totalLogs = res.data?.result?.reduce((acc, stream) => acc + (stream.values?.length || 0), 0) || 0
      const streams = res.data?.result?.length || 0
      const queryTime = Date.now() - queryStartTime
      console.log('[LokiPage] Query summary:', {totalLogs, streams, queryTime})

      try {
        const volRes = await getLogVolume(selector, {start: Math.round(startNs), end: Math.round(endNs), step: Math.max(60, Math.floor(rangeMinutes*60 / 60))})
        console.log('[LokiPage] Volume response:', volRes)
        const vals = (volRes.data && volRes.data.result && volRes.data.result[0] && volRes.data.result[0].values) ? volRes.data.result[0].values.map(v=>Number(v[1])) : []
        console.log('[LokiPage] Volume data parsed:', vals)
        if(vals.length > 0 && vals.some(v => v > 0)) {
          setVolume(vals)
          console.log('[LokiPage] Volume set to:', vals)
        } else {
          // Fallback: calculate from results
          const buckets = {}
          if(res.data?.result) {
            res.data.result.forEach(stream => {
              stream.values?.forEach(([ts]) => {
                const bucket = Math.floor(parseInt(ts) / 1e9 / 60)
                buckets[bucket] = (buckets[bucket] || 0) + 1
              })
            })
            const volumeData = Object.values(buckets).slice(-60)
            console.log('[LokiPage] Fallback volume data:', volumeData)
            if(volumeData.length > 0) {
              setVolume(volumeData)
            } else if(totalLogs > 0) {
              // Single data point from total
              const singlePoint = Array(10).fill(Math.ceil(totalLogs / 10))
              console.log('[LokiPage] Single point volume:', singlePoint)
              setVolume(singlePoint)
            } else {
              setVolume([0])
            }
          }
        }
      } catch(volErr) {
        console.warn('Failed to fetch log volume:', volErr)
        // Create simple volume from log count
        if(totalLogs > 0) {
          const singlePoint = Array(10).fill(Math.ceil(totalLogs / 10))
          setVolume(singlePoint)
        } else {
          setVolume([0])
        }
      }
    }catch(e){
      setError(e.message)
    }finally{
      setLoading(false)
    }
  }
  
  function applyQuickSelector(selector){
    console.log('[LokiPage] applyQuickSelector:', selector)
    setSelectedFilters(selector.filters)
    setPattern(selector.pattern)
    setRangeMinutes(60)
    runQueryWithFilters(selector.filters, selector.pattern)
  }
  
  async function runQueryWithFilters(filters, textPattern){
    setError(null)
    setLoading(true)
    const queryStartTime = Date.now()
    
    try{
      let q
      let selectorForVolume
      if(queryMode === 'custom') {
        q = customLogQL.trim()
        if(!q) {
          setError('Please enter a LogQL query')
          setLoading(false)
          return
        }
        selectorForVolume = buildSelectorFromFilters(filters)
      } else {
        const selector = buildSelectorFromFilters(filters)
        selectorForVolume = selector
        q = selector
        if(textPattern) q += ` |= "${textPattern}"`
      }
      
      const start = Date.now() - rangeMinutes*60*1000
      const startNs = start * 1e6
      const endNs = Date.now() * 1e6
      
      setLastQuery(q)

      const res = await queryLogs({query: q, start: Math.round(startNs), end: Math.round(endNs), limit: maxLogs})
      setQueryResult(res)
      // update quick-search suggestions
      try {
        const terms = computeTopTermsFromResult(res, 12)
        setTopTerms(terms)
      } catch (err) {
        console.warn('Failed to compute top terms:', err)
        setTopTerms([])
      }
      
      const totalLogs = res.data?.result?.reduce((acc, stream) => acc + (stream.values?.length || 0), 0) || 0
      const streams = res.data?.result?.length || 0
      const queryTime = Date.now() - queryStartTime
      console.log('[LokiPage] Query summary:', {totalLogs, streams, queryTime})

      try {
        const volRes = await getLogVolume(selectorForVolume, {start: Math.round(startNs), end: Math.round(endNs), step: Math.max(60, Math.floor(rangeMinutes*60 / 60))})
        console.log('[LokiPage] Volume response:', volRes)
        const vals = (volRes.data && volRes.data.result && volRes.data.result[0] && volRes.data.result[0].values) ? volRes.data.result[0].values.map(v=>Number(v[1])) : []
        if(vals.length > 0 && vals.some(v => v > 0)) {
          setVolume(vals)
        } else {
          // Fallback calculation
          const buckets = {}
          if(res.data?.result) {
            res.data.result.forEach(stream => {
              stream.values?.forEach(([ts]) => {
                const bucket = Math.floor(parseInt(ts) / 1e9 / 60)
                buckets[bucket] = (buckets[bucket] || 0) + 1
              })
            })
            const volumeData = Object.values(buckets).slice(-60)
            if(volumeData.length > 0) {
              setVolume(volumeData)
            } else if(totalLogs > 0) {
              const singlePoint = Array(10).fill(Math.ceil(totalLogs / 10))
              setVolume(singlePoint)
            } else {
              setVolume([0])
            }
          }
        }
      } catch(volErr) {
        console.warn('Failed to fetch volume:', volErr)
        if(totalLogs > 0) {
          const singlePoint = Array(10).fill(Math.ceil(totalLogs / 10))
          setVolume(singlePoint)
        } else {
          setVolume([0])
        }
      }
    }catch(err){
      console.error('Query error:', err)
      setError(err.message || 'Failed to query logs')
    }finally{
      setLoading(false)
    }
  }
  
  function buildSelectorFromFilters(filters){
    if(!filters || !filters.length) {
      // Use first available label or fallback to common label
      const firstLabel = labels[0] || 'service_name'
      return `{${firstLabel}=~".+"}`  
    }
    const parts = filters.map(f=>`${f.label}="${f.value}"`)
    return `{${parts.join(',')}}`
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-sre-text mb-2">Loki — Log Aggregation</h1>
          <p className="text-sre-text-muted">Query and analyze logs using LogQL</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-sre-text">
            <input 
              type="checkbox" 
              checked={autoRefresh} 
              onChange={(e)=>setAutoRefresh(e.target.checked)}
              className="rounded border-sre-border bg-sre-surface"
            />
            Auto-refresh
          </label>
          {autoRefresh && (
            <select 
              value={refreshInterval} 
              onChange={(e)=>setRefreshInterval(Number(e.target.value))}
              className="px-2 py-1 bg-sre-surface border border-sre-border rounded text-sm text-sre-text"
            >
              <option value={10}>10s</option>
              <option value={30}>30s</option>
              <option value={60}>60s</option>
              <option value={300}>5m</option>
            </select>
          )}
        </div>
      </div>

      {error && (
        <Alert variant="error" className="mb-6">
          <strong>Error:</strong> {error}
        </Alert>
      )}
      
          {/* Stats Bar */}
      

      <Card title="Search & Filter" subtitle="Build LogQL queries using labels and patterns" className="mb-6">
        <form onSubmit={runQuery} className="space-y-4">
          <div className="flex items-center gap-4 pb-3 border-b border-sre-border">
            <span className="text-sm text-sre-text-muted flex items-center">
              <span className="material-icons text-sm mr-1">build</span>
              Mode:
            </span>
            <label className="flex items-center gap-2 cursor-pointer">
              <input 
                type="radio" 
                value="builder" 
                checked={queryMode === 'builder'} 
                onChange={(e) => setQueryMode(e.target.value)}
                className="text-sre-primary focus:ring-sre-primary"
              />
              <span className="text-sm text-sre-text">Filter Builder</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input 
                type="radio" 
                value="custom" 
                checked={queryMode === 'custom'} 
                onChange={(e) => setQueryMode(e.target.value)}
                className="text-sre-primary focus:ring-sre-primary"
              />
              <span className="text-sm text-sre-text">Custom LogQL</span>
            </label>
          </div>

          {queryMode === 'custom' ? (
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                <span className="material-icons text-sm mr-1 align-middle">code</span>
                LogQL Query
              </label>
              <textarea
                value={customLogQL}
                onChange={(e) => setCustomLogQL(e.target.value)}
                placeholder='{job="myapp"} |= "error" | json'
                rows={4}
                className="w-full px-3 py-2 bg-sre-surface border border-sre-border rounded-lg text-sre-text font-mono text-sm focus:border-sre-primary focus:ring-1 focus:ring-sre-primary resize-none"
              />
              <p className="text-xs text-sre-text-muted mt-1">
                Enter a LogQL query directly. Example: <code className="px-1 py-0.5 bg-sre-surface-light rounded">{'{level="error"} |= "timeout"'}</code>
              </p>
            </div>
          ) : (
            <>
          <div className="flex gap-2 pb-4 border-b border-sre-border flex-wrap">
            <span className="text-sm text-sre-text-muted mr-2 flex items-center">
              <span className="material-icons text-sm mr-1">filter_list</span>
              Quick:
            </span>
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={()=>applyQuickSelector({label:'All Logs', filters: [], pattern:''})}
              type="button"
              className="flex items-center gap-1"
            >
              <span className="material-icons text-sm">list</span>
              All Logs
            </Button>
            {Object.entries(labelValuesCache).slice(0, 1).map(([label, values]) => (
              Array.isArray(values) && values.slice(0, 3).map((value, idx) => (
                <Button 
                  key={`${label}-${value}`}
                  variant="ghost" 
                  size="sm" 
                  onClick={()=>applyQuickSelector({label:value, filters: [{label, value}], pattern:''})}
                  type="button"
                  className="flex items-center gap-1"
                >
                  <span className="material-icons text-sm text-blue-500">label</span>
                  {value}
                </Button>
              ))
            ))}
            {(selectedFilters.length > 0 || pattern) && (
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={()=>{setSelectedFilters([]); setPattern(''); setTimeout(() => runQuery(), 0)}}
                type="button"
                className="flex items-center gap-1 text-red-500 hover:text-red-600"
              >
                <span className="material-icons text-sm">clear</span>
                Clear
              </Button>
            )}
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">Label</label>
              <select 
                value={selectedLabel} 
                onChange={(e)=>{setSelectedLabel(e.target.value); setSelectedValue(''); loadLabelValues(e.target.value)}} 
                className="w-full px-3 py-2 bg-sre-surface border border-sre-border rounded-lg text-sre-text focus:border-sre-primary focus:ring-1 focus:ring-sre-primary"
              >
                <option value="">-- Select label --</option>
                {(labels || []).length === 0 && (
                  <option value="" disabled>No labels available</option>
                )}
                {(labels || []).map(l=> <option key={l} value={l}>{l}</option>)}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">Value</label>
              <select 
                value={selectedValue} 
                onChange={(e)=>setSelectedValue(e.target.value)} 
                className="w-full px-3 py-2 bg-sre-surface border border-sre-border rounded-lg text-sre-text focus:border-sre-primary focus:ring-1 focus:ring-sre-primary"
                disabled={!selectedLabel}
              >
                <option value="">
                  {loadingValues[selectedLabel] ? 'Loading...' : '-- Select value --'}
                </option>
                {selectedLabel && !loadingValues[selectedLabel] && (
                  <option value="__any__">Any value</option>
                )}
                {(Array.isArray(labelValuesCache[selectedLabel]) ? labelValuesCache[selectedLabel] : []).map(v=> <option key={v} value={v}>{v}</option>)}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">Text Filter</label>
              <input 
                value={pattern} 
                onChange={(e)=>setPattern(e.target.value)} 
                placeholder='e.g., "timeout"' 
                className="w-full px-3 py-2 bg-sre-surface border border-sre-border rounded-lg text-sre-text focus:border-sre-primary focus:ring-1 focus:ring-sre-primary" 
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">Time Range</label>
              <select 
                value={rangeMinutes} 
                onChange={(e)=>setRangeMinutes(Number(e.target.value))} 
                className="w-full px-3 py-2 bg-sre-surface border border-sre-border rounded-lg text-sre-text focus:border-sre-primary focus:ring-1 focus:ring-sre-primary"
              >
                <option value={5}>Last 5 minutes</option>
                <option value={15}>Last 15 minutes</option>
                <option value={60}>Last 1 hour</option>
                <option value={180}>Last 3 hours</option>
                <option value={360}>Last 6 hours</option>
                <option value={1440}>Last 24 hours</option>
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">Max Logs</label>
              <select 
                value={maxLogs} 
                onChange={(e)=>setMaxLogs(Number(e.target.value))} 
                className="w-full px-3 py-2 bg-sre-surface border border-sre-border rounded-lg text-sre-text focus:border-sre-primary focus:ring-1 focus:ring-sre-primary"
              >
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={500}>500</option>
                <option value={1000}>1000</option>
                <option value={5000}>5000</option>
              </select>
            </div>
          </div>
          </>
          )}

          <div className="flex items-center gap-2">
            {queryMode === 'builder' && (
              <>
            <Button type="button" onClick={addFilter} disabled={!selectedLabel || !selectedValue}>
              Add Filter
            </Button>
            {selectedFilters.length > 0 && (
              <Button type="button" variant="ghost" onClick={clearAllFilters}>
                Clear All
              </Button>
            )}
              </>
            )}
            <div className="flex-1" />
            <Button type="submit" loading={loading} className="px-8">
              {loading ? 'Searching...' : 'Run Query'}
            </Button>
          </div>

          {selectedFilters.length>0 && (
            <div className="mt-2 flex gap-2 flex-wrap">
              {selectedFilters.map((f, i)=> (
                <div key={i} className="inline-flex items-center gap-2 px-3 py-1.5 bg-sre-primary/10 border border-sre-primary/30 rounded-full">
                  <span className="text-xs font-mono text-sre-primary font-semibold">{f.label}</span>
                  <span className="text-xs font-mono text-sre-text">=</span>
                  <span className="text-sm font-semibold text-sre-text">{f.value}</span>
                  <button onClick={()=>removeFilter(i)} className="text-sre-text-muted hover:text-sre-text ml-1">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}
          
          {lastQuery && (
            <div className="pt-2 border-t border-sre-border">
              <div className="flex items-center justify-between">
                <div className="text-xs text-sre-text-muted">LogQL Query:</div>
                <button 
                  type="button"
                  onClick={()=>copyToClipboard(lastQuery)}
                  className="text-xs text-sre-primary hover:underline"
                >
                  Copy
                </button>
              </div>
              <code className="block mt-1 text-xs font-mono bg-sre-bg-alt p-2 rounded border border-sre-border text-sre-text">
                {lastQuery}
              </code>
            </div>
          )}
        </form>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <Card title="Log Results" subtitle={queryResult && queryResult.data?.result?.length ? `Showing results` : 'Run a query'} className="lg:col-span-3">
          {/* View Controls */}
          {queryResult && queryResult.data?.result?.length > 0 && (
            <div className="mb-4 flex items-center justify-between pb-4 border-b border-sre-border">
              <div className="flex items-center gap-4">
                <div className="flex gap-1 bg-sre-bg-alt rounded-lg p-1">
                  {['table', 'compact', 'raw'].map(mode => (
                    <button
                      key={mode}
                      onClick={()=>setViewMode(mode)}
                      className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                        viewMode === mode 
                          ? 'bg-sre-primary text-white' 
                          : 'text-sre-text-muted hover:text-sre-text'
                      }`}
                    >
                      {mode.charAt(0).toUpperCase() + mode.slice(1)}
                    </button>
                  ))}
                </div>
                
                <input 
                  type="text"
                  value={searchText}
                  onChange={(e)=>setSearchText(e.target.value)}
                  placeholder="Filter displayed logs..."
                  className="px-3 py-1 bg-sre-surface border border-sre-border rounded text-sm text-sre-text w-64"
                />
              </div>
              
                      <div className="flex gap-2">
                        <Button size="sm" variant="ghost" onClick={downloadLogs}>
                  <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Export
                </Button>
                
              </div>
            </div>
          )}
          
          {loading ? (
            <div className="py-12 flex flex-col items-center ">
              <Spinner size="lg" />
              <p className="text-sre-text-muted mt-4">Querying logs...</p>
            </div>
          ) : queryResult && queryResult.data && queryResult.data.result && queryResult.data.result.length ? (
            <div className="space-y-4  overflow-auto p-3 scrollbar-thin h-[70rem]">
              {queryResult.data.result.map((stream, streamIdx)=> {
                const filteredValues = filterDisplayedLogs(stream.values)
                if(filteredValues.length === 0) return null
                
                return (
                  <div key={streamIdx} className="border border-sre-border rounded-lg overflow-hidden">
                    {/* Stream Header */}
                    <div className="bg-sre-bg-alt px-4 py-2 border-b border-sre-border">
                      <div className="flex items-center justify-between">
                        <div className="flex flex-wrap gap-2">
                          {stream.stream && Object.entries(stream.stream).map(([k,v])=> (
                            <span key={k} className="inline-flex items-center gap-1 px-2 py-0.5 bg-sre-surface border border-sre-border rounded text-xs font-mono">
                              <span className="text-sre-primary font-semibold">{k}</span>
                              <span className="text-sre-text-muted">=</span>
                              <span className="text-sre-text">{v}</span>
                            </span>
                          ))}
                        </div>
                        <Badge variant="secondary">{filteredValues.length}</Badge>
                      </div>
                    </div>
                    
                    {/* Log Entries */}
                    <div className="divide-y divide-sre-border">
                      {filteredValues.slice().reverse().slice(0, viewMode === 'compact' ? 200 : 100).map((v,i)=> {
                        const formatted = formatLogLine(v[1])
                        const logKey = `${streamIdx}-${v[0]}-${v[1].substring(0, 50).replace(/[^a-zA-Z0-9]/g, '')}`
                        const isExpanded = expandedLogs[logKey]
                        const badge = getLogLevelBadge(v[1])
                        
                        if(viewMode === 'compact'){
                          return (
                            <div key={i} className="px-4 py-2 hover:bg-sre-surface/50 transition-colors text-xs font-mono">
                              <span className="text-sre-text-muted mr-3">{formatNsToIso(v[0]).substring(11,19)}</span>
                              <span className={`${badge.class} px-2 py-0.5 rounded text-[10px] font-bold mr-2`}>
                                {badge.text}
                              </span>
                              <span className={getLogLevelColor(v[1])}>{v[1].substring(0, 150)}{v[1].length > 150 ? '...' : ''}</span>
                            </div>
                          )
                        }
                        
                        if(viewMode === 'raw'){
                          return (
                            <div key={i} className="px-4 py-2 hover:bg-sre-surface/50 transition-colors">
                              <pre className="text-xs font-mono text-sre-text whitespace-pre-wrap break-all">
                                {JSON.stringify({timestamp: v[0], log: v[1]}, null, 2)}
                              </pre>
                            </div>
                          )
                        }
                        
                        return (
                          <div key={i} className="px-4 py-3 hover:bg-sre-surface/50 transition-colors">
                            <div className="flex items-start justify-between mb-2">
                              <div className="flex items-center gap-3">
                                <span className={`${badge.class} px-2 py-1 rounded text-[10px] font-bold border`}>
                                  {badge.text}
                                </span>
                                <div className="text-xs text-sre-text-muted">
                                  <div className="font-semibold">{formatNsToIso(v[0])}</div>
                                  <div className="text-[10px]">{formatRelativeTime(v[0])}</div>
                                </div>
                              </div>
                              <div className="flex items-center gap-2">
                                <button 
                                  onClick={()=>copyToClipboard(v[1])}
                                  className="p-1 hover:bg-sre-bg-alt rounded text-sre-text-muted hover:text-sre-text"
                                  title="Copy log"
                                >
                                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                                  </svg>
                                </button>
                                {formatted.type === 'json' && (
                                  <button 
                                    onClick={()=>toggleLogExpand(logKey)}
                                    className="p-1 hover:bg-sre-bg-alt rounded text-sre-text-muted hover:text-sre-text"
                                  >
                                    <svg className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                    </svg>
                                  </button>
                                )}
                              </div>
                            </div>
                            
                            {formatted.type === 'json' ? (
                              <div className="mt-2 space-y-1">
                                {Object.entries(formatted.data).slice(0, isExpanded ? undefined : 5).map(([key, val]) => (
                                  <div key={key} className="flex gap-3 text-sm">
                                    <span className="text-sre-primary font-semibold min-w-[120px] font-mono">{key}:</span>
                                    <span className={`${getLogLevelColor(String(val))} flex-1 font-mono break-all`}>
                                      {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                                    </span>
                                  </div>
                                ))}
                                {!isExpanded && Object.keys(formatted.data).length > 5 && (
                                  <button 
                                    onClick={()=>toggleLogExpand(logKey)}
                                    className="text-xs text-sre-primary hover:underline mt-2"
                                  >
                                    Show {Object.keys(formatted.data).length - 5} more fields...
                                  </button>
                                )}
                              </div>
                            ) : (
                              <div className={`mt-2 text-sm font-mono ${getLogLevelColor(formatted.data)} break-all`}>
                                {isExpanded ? formatted.data : (formatted.data.length > 300 ? formatted.data.substring(0, 300) + '...' : formatted.data)}
                                {!isExpanded && formatted.data.length > 300 && (
                                  <button 
                                    onClick={()=>toggleLogExpand(logKey)}
                                    className="text-xs text-sre-primary hover:underline ml-2"
                                  >
                                    Show more
                                  </button>
                                )}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="text-center py-16">
              <svg className="w-20 h-20 mx-auto text-sre-text-subtle mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p className="text-lg text-sre-text-muted mb-2">No logs found</p>
              <p className="text-sm text-sre-text-subtle">Try adjusting your filters or expanding the time range</p>
            </div>
          )}
        </Card>

        <div className="space-y-6">
          {/* Log Volume Chart */}
          {showTimeline && volume.length > 0 && (
            <Card title="Log Volume" subtitle="Over time">
              <div className="mb-3 w-full overflow-hidden">
                <Sparkline 
                  data={volume} 
                  width={280} 
                  height={100} 
                  stroke="#60a5fa" 
                  strokeWidth={2}
                  fill="rgba(96, 165, 250, 0.2)"
                />
              </div>
              <div className="grid grid-cols-3 gap-3 text-xs">
                <div className="bg-sre-surface border border-sre-border rounded-lg p-2">
                  <div className="text-sre-text-muted mb-1">Total</div>
                  <div className="text-base font-bold text-sre-text">
                    {volume.reduce((a,b)=>a+b, 0).toLocaleString()}
                  </div>
                </div>
                <div className="bg-sre-surface border border-sre-border rounded-lg p-2">
                  <div className="text-sre-text-muted mb-1">Avg/min</div>
                  <div className="text-base font-bold text-sre-text">
                    {Math.round(volume.reduce((a,b)=>a+b, 0) / volume.length).toLocaleString()}
                  </div>
                </div>
                <div className="bg-sre-surface border border-sre-border rounded-lg p-2">
                  <div className="text-sre-text-muted mb-1">Peak</div>
                  <div className="text-base font-bold text-sre-text">
                    {Math.max(...volume).toLocaleString()}
                  </div>
                </div>
              </div>
            </Card>
          )}
          
          {/* Quick Filters */}
          <Card title="Quick Filters" subtitle="Filter by labels">
            <div className="space-y-3">
              {/* Dynamic filters for each label with values */}
              {Object.entries(labelValuesCache).map(([label, values]) => (
                Array.isArray(values) && values.length > 0 && (
                  <div key={label}>
                    <div className="text-xs text-sre-text-muted mb-2 font-medium capitalize">{label.replace(/_/g, ' ')}</div>
                    <div className="space-y-1">
                      {values.map((value) => (
                        <button
                          key={`${label}-${value}`}
                          onClick={()=>{
                            setSelectedFilters([{label, value}])
                            setPattern('')
                            runQueryWithFilters([{label, value}], '')
                          }}
                          className="w-full flex items-center justify-between px-3 py-2 bg-sre-surface border border-sre-border rounded-lg hover:border-sre-primary transition-colors text-left group"
                        >
                          <span className="text-sm text-sre-text flex items-center">
                            <span className="material-icons text-base mr-2 text-blue-500">label</span>
                            {value}
                          </span>
                          <span className="material-icons text-sre-text-muted text-sm group-hover:text-sre-primary transition-colors">arrow_forward</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )
              ))}
              
              {/* Dynamic Text Patterns derived from recent query results */}
              {Object.keys(labelValuesCache).length > 0 && (
                <div>
                  <div className="text-xs text-sre-text-muted mb-2 font-medium">Text Search</div>
                  <div className="space-y-1">
                    {topTerms && topTerms.length > 0 ? (
                      topTerms.map((t) => (
                        <button
                          key={t.term}
                          onClick={()=>{
                            setSelectedFilters([])
                            setPattern(t.term)
                            runQueryWithFilters([], t.term)
                          }}
                          className="w-full flex items-center justify-between px-3 py-2 bg-sre-surface border border-sre-border rounded-lg hover:border-sre-primary transition-colors text-left group"
                          title={`Use "${t.term}" as a quick text search (seen ${t.count} times)`}
                        >
                          <span className="text-sm text-sre-text flex items-center">
                            <span className={`material-icons text-base mr-2 ${t.iconClass || 'text-sre-text'}`}>{t.icon || 'search'}</span>
                            "{t.term}"
                          </span>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-sre-text-muted">{t.count}</span>
                            <span className="material-icons text-sre-text-muted text-sm group-hover:text-sre-primary transition-colors">arrow_forward</span>
                          </div>
                        </button>
                      ))
                    ) : (
                      <div className="text-xs text-sre-text-muted">No text examples found from recent results. Run a query to populate suggestions.</div>
                    )}
                  </div>
                </div>
              )}
              
              {/* No data message */}
              {Object.keys(labelValuesCache).length === 0 && (
                <div className="text-center py-4 text-sm text-sre-text-muted">
                  <span className="material-icons text-2xl mb-2 opacity-50">filter_list_off</span>
                  <p>No labels available yet.</p>
                  <p className="text-xs mt-1">Try running a query first.</p>
                </div>
              )}
            </div>
          </Card>
          
          {/* Labels Info */}
          <Card title="Available Labels" subtitle={`${labels.length} labels`}>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {labels.map(label => (
                <div key={label} className="flex items-center justify-between text-sm">
                  <span className="font-mono text-sre-text">{label}</span>
                  <Badge variant="secondary" size="sm">
                    {labelValuesCache[label]?.length || '...'}
                  </Badge>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
