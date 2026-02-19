`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { useCallback, useEffect, useMemo, useState } from 'react'
import PageHeader from '../components/ui/PageHeader'
import { Card, Input, Button, Select, Spinner, Badge } from '../components/ui'
import { getAuditLogs, exportAuditLogs, getUsers } from '../api'
import { useToast } from '../contexts/ToastContext'
import { useAuth } from '../contexts/AuthContext'
import { copyToClipboard } from '../utils/helpers' 

const DEFAULT_LIMIT = 100
const LIMIT_OPTIONS = [25, 50, 100, 250]

function toIso(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  return d.toISOString()
}

function formatLocal(dt) {
  if (!dt) return '-'
  try {
    return new Date(dt).toLocaleString('en-GB', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch (e) {
    return dt
  }
}

function prettyJson(obj) {
  try {
    return JSON.stringify(obj || {}, null, 2)
  } catch (e) {
    return String(obj)
  }
}

function highlight(text = '', q = '') {
  if (!q) return text
  const idx = text.toLowerCase().indexOf(q.toLowerCase())
  if (idx === -1) return text
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-yellow-100 rounded px-0.5">{text.slice(idx, idx + q.length)}</mark>
      {text.slice(idx + q.length)}
    </>
  )
}

export default function AuditCompliancePage() {
  const { hasPermission } = useAuth()
  const toast = useToast()
  const [items, setItems] = useState([])
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [selected, setSelected] = useState(null)
  const [hasMore, setHasMore] = useState(false)

  const [filters, setFilters] = useState({
    start: '',
    end: '',
    user_id: '',
    action: '',
    resource_type: '',
    q: '',
    limit: DEFAULT_LIMIT,
    offset: 0,
  })

  const canView = hasPermission('read:audit_logs')

  const loadUsers = useCallback(async () => {
    try {
      const data = await getUsers()
      setUsers(Array.isArray(data) ? data : [])
    } catch {
      setUsers([])
    }
  }, [])

  const loadAudit = useCallback(async (baseFilters, { commit = true } = {}) => {
    setLoading(true)
    try {
      const queryFilters = baseFilters || {}
      const requestedLimit = Number(queryFilters.limit) || DEFAULT_LIMIT
      const params = {
        ...queryFilters,
        start: toIso(queryFilters.start),
        end: toIso(queryFilters.end),
        limit: requestedLimit + 1,
      }
      const data = await getAuditLogs(params)
      const list = Array.isArray(data) ? data : []
      const nextHasMore = list.length > requestedLimit
      const pageItems = list.slice(0, requestedLimit)

      if (commit) {
        setHasMore(nextHasMore)
        setItems(pageItems)
      }

      return { items: pageItems, hasMore: nextHasMore }
    } catch (err) {
      toast.error(err?.body?.detail || err?.message || 'Failed to load audit logs')
      if (commit) {
        setItems([])
        setHasMore(false)
      }
      return null
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    loadUsers()
  }, [])

  const userLabelById = useMemo(() => {
    const map = {}
    users.forEach((u) => {
      map[u.id] = `${u.username || u.id}${u.email ? ` <${u.email}>` : ''}`
    })
    return map
  }, [users])

  const handleExportCsv = async () => {
    setExporting(true)
    try {
      const text = await exportAuditLogs({
        ...filters,
        start: toIso(filters.start),
        end: toIso(filters.end),
      })
      const { downloadFile } = await import('../utils/helpers')
      downloadFile(typeof text === 'string' ? text : JSON.stringify(text), 'audit-logs.csv', 'text/csv')
      toast.success('Audit CSV exported')
    } catch (err) {
      toast.error(err?.body?.detail || err?.message || 'Failed to export audit logs')
    } finally {
      setExporting(false)
    }
  }

  const applyPage = useCallback(async (nextFilters, { allowEmpty = true } = {}) => {
    const page = await loadAudit(nextFilters, { commit: false })
    if (!page) return false
    if (!allowEmpty && page.items.length === 0) return false
    setFilters(nextFilters)
    setItems(page.items)
    setHasMore(page.hasMore)
    return true
  }, [loadAudit])

  useEffect(() => {
    loadAudit(filters)
  }, [])

  const onLimitChange = async (v) => {
    const nextFilters = { ...filters, limit: Number(v), offset: 0 }
    await applyPage(nextFilters)
  }

  const onPrev = async () => {
    if (loading || filters.offset === 0) return
    const nextFilters = { ...filters, offset: Math.max(0, filters.offset - filters.limit) }
    await applyPage(nextFilters)
  }

  const onNext = async () => {
    if (loading || items.length === 0) return
    const nextFilters = { ...filters, offset: filters.offset + filters.limit }
    const moved = await applyPage(nextFilters, { allowEmpty: false })
    if (!moved) {
      toast.success('No more audit records')
    }
  }

  const canNext = !loading && items.length > 0
  const pageStart = items.length ? filters.offset + 1 : 0
  const pageEnd = items.length ? Math.min(filters.offset + items.length, filters.offset + filters.limit) : 0
  const pageLabel = `Showing ${pageStart} - ${pageEnd} (limit ${filters.limit})`

  const copyText = useCallback(async (text) => {
    const ok = await copyToClipboard(typeof text === 'string' ? text : JSON.stringify(text))
    if (ok) toast.success('Copied to clipboard')
    else toast.error('Copy failed')
    return ok
  }, [toast])

  const clearFilter = (key) => {
    const nextFilters = { ...filters, [key]: '', offset: 0 }
    applyPage(nextFilters)
  }

  const clearAllFilters = () => {
    const nextFilters = { start: '', end: '', user_id: '', action: '', resource_type: '', q: '', limit: filters.limit, offset: 0 }
    applyPage(nextFilters)
  }

  if (!canView) {
    return <div className="text-center py-12 text-sre-text-muted">You do not have permission to view audit logs.</div>
  }

  return (
    <div className="animate-fade-in max-w-7xl mx-auto">
      <PageHeader icon="policy" title="Audit & Compliance" subtitle="Who viewed what, who changed resources, and token lifecycle events." />

      <Card className="mb-4">
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 w-full">
            <div>
              <Input
                type="datetime-local"
                label="Start"
                helperText="dd/mm/yyyy, hh:mm"
                className="h-10 max-w-full"
                value={filters.start}
                onChange={(e) => setFilters((prev) => ({ ...prev, start: e.target.value }))}
              />
            </div>

            <div>
              <Input
                type="datetime-local"
                label="End"
                helperText="dd/mm/yyyy, hh:mm"
                className="h-10 max-w-full"
                value={filters.end}
                onChange={(e) => setFilters((prev) => ({ ...prev, end: e.target.value }))}
              />
            </div>

            <div>
              <Select
                label="User"
                value={filters.user_id}
                className="h-10 max-w-full"
                onChange={(e) => setFilters((prev) => ({ ...prev, user_id: e.target.value }))}
              >
                <option value="">All users</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>{u.username} {u.email ? `<${u.email}>` : ''}</option>
                ))}
              </Select>
            </div>

            <Input label="Action" className="h-10 " placeholder="e.g. api_key.create" value={filters.action} onChange={(e) => setFilters((prev) => ({ ...prev, action: e.target.value }))} />
            <Input label="Resource type" className="h-10" placeholder="e.g. api_keys" value={filters.resource_type} onChange={(e) => setFilters((prev) => ({ ...prev, resource_type: e.target.value }))} />
            <Input label="Search details" className="h-10" placeholder="Text in details JSON" value={filters.q} onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))} />

            {/* Controls: placed inside the same grid so they align with filter inputs */}
            <div className="col-span-1 md:col-span-2 xl:col-span-3 flex items-end justify-start gap-6 mt-5">
              <Select value={filters.limit} onChange={(e) => onLimitChange(e.target.value)} className="h-10 w-20">
                {LIMIT_OPTIONS.map((l) => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </Select>

              <div className="flex gap-2">
                <Button
                  size="sm"
                  className="min-w-[110px] h-10"
                  onClick={async () => {
                    const nextFilters = { ...filters, offset: 0 }
                    await applyPage(nextFilters)
                  }}
                >
                  Apply
                </Button>

                <Button size="sm" variant="secondary" className="min-w-[110px] h-10" onClick={handleExportCsv} disabled={exporting}>
                  {exporting ? <span className="inline-flex items-center gap-2"><Spinner size="xs" /> Exporting...</span> : 'Export'}
                </Button>
                <Button size="sm" variant="ghost" className="h-10" onClick={clearAllFilters}>Clear</Button>
              </div>
            </div>
          </div>
        </div>

        {/* active filter chips */}
        <div className="mt-3 flex flex-wrap gap-2">
          {filters.user_id && <Badge variant="info" className="px-2">User: {userLabelById[filters.user_id] || filters.user_id} <button onClick={() => clearFilter('user_id')} className="ml-2">✕</button></Badge>}
          {filters.action && <Badge className="px-2">Action: {filters.action} <button onClick={() => clearFilter('action')} className="ml-2">✕</button></Badge>}
          {filters.resource_type && <Badge className="px-2">Resource: {filters.resource_type} <button onClick={() => clearFilter('resource_type')} className="ml-2">✕</button></Badge>}
          {filters.q && <Badge className="px-2">Search: {filters.q} <button onClick={() => clearFilter('q')} className="ml-2">✕</button></Badge>}
        </div>

        <div className="mt-3 flex items-center justify-between text-xs text-sre-text-muted">
          <div aria-live="polite">{pageLabel}</div>
          <div className="flex gap-2 items-center">


            <Button size="sm" variant="ghost" onClick={onPrev} disabled={filters.offset === 0 || loading}>Previous</Button>

            <Button size="sm" variant="ghost" onClick={onNext} disabled={!canNext}>Next</Button>


          </div>
        </div>
      </Card>

      <Card className="p-0 overflow-hidden">
        {loading ? (
          <div className="p-6">
            <div className="animate-pulse space-y-2">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="h-6 bg-sre-surface rounded" />
              ))}
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto scrollbar-thin scrollbar-thumb-sre-border scrollbar-track-transparent">
            <table className="min-w-full table-fixed text-left text-sm">
              <thead>
                <tr className="bg-sre-surface text-sre-text-muted text-xs uppercase tracking-wide sticky top-0 z-10">
                  <th className="py-3 px-4 w-[220px]">Timestamp</th>
                  <th className="py-3 px-4 w-[240px]">User</th>
                  <th className="py-3 px-4 w-[180px]">Action</th>
                  <th className="py-3 px-4">Resource</th>
                  <th className="py-3 px-4 w-[140px]">HTTP</th>
                  <th className="py-3 px-4 w-[120px]">IP</th>
                  <th className="py-3 px-4">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {items.map((row) => {
                  const details = row.details || {}
                  const method = details.method || ''
                  const status = details.status_code || ''
                  const resource = row.resource_type ? `[${row.resource_type}]${row.resource_id ? ` (${row.resource_id})` : ''}` : '-'
                  return (
                    <tr
                      key={row.id}
                      role="button"
                      aria-label={`Open audit details ${row.id}`}
                      className="align-top hover:bg-sre-surface/50"
                      tabIndex={0}
                      onClick={() => setSelected(row)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          setSelected(row)
                        }
                      }}
                    >
                      <td className="py-3 px-4 whitespace-nowrap align-middle">{formatLocal(row.created_at)}</td>
                      <td className="py-3 px-4 align-middle truncate">{userLabelById[row.user_id] || row.username || row.user_id || 'system'}</td>
                      <td className="py-3 px-4 font-medium align-middle truncate">{highlight(row.action || '-', filters.q)}</td>
                      <td className="py-3 px-4 align-middle truncate max-w-[240px]">{resource}</td>
                      <td className="py-3 px-4 align-middle">
                        {method && <span className="inline-block px-2 py-0.5 mr-2 rounded text-xs bg-sre-surface-variant">{method}</span>}
                        {status && <span className="inline-block px-2 py-0.5 rounded text-xs bg-green-100 text-green-800">{status}</span>}
                      </td>
                      <td className="py-3 px-4 align-middle">{row.ip_address || '-'}</td>
                      <td className="py-3 px-4 align-middle max-w-[420px] truncate" title={JSON.stringify(details)}>
                        <div className="flex items-center gap-2">
                          <div className="truncate text-xs text-sre-text-muted flex-1">{highlight(JSON.stringify(details), filters.q)}</div>
                          <div className="flex-shrink-0 flex gap-2">
                            <button className="px-2 py-1 rounded-md text-sre-text-muted hover:text-sre-text hover:bg-sre-surface cursor-pointer text-xs" onClick={(e) => { e.stopPropagation(); setSelected(row) }}>View</button>
                            <button className="px-2 py-1 rounded-md text-sre-text-muted hover:text-sre-text hover:bg-sre-surface cursor-pointer text-xs" onClick={(e) => { e.stopPropagation(); copyText(prettyJson(details)) }}>Copy</button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )
                })}

                {items.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-12 px-4 text-sre-text-muted text-center">
                      No audit records found for the current filters.
                      <div className="mt-3 text-xs">Try widening the date range, removing filters, or increasing the limit.</div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>

          </div>
        )}

        <div className="p-4 flex items-center justify-center">
          <div className="text-xs text-sre-text-muted">{items.length ? 'End of results' : ''}</div>
        </div>
      </Card>

      {selected && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 flex items-center justify-center" onClick={() => setSelected(null)}>
          <div className="bg-sre-surface border border-sre-border rounded-2xl shadow-lg max-w-6xl w-full p-0 m-4 overflow-hidden" onClick={(e) => e.stopPropagation()}>
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 p-5 border-b border-sre-border bg-sre-surface/70">
              <div className="flex items-start gap-4 min-w-0">
                <div className="w-12 h-12 rounded-lg bg-sre-primary/10 text-sre-primary flex items-center justify-center font-semibold text-lg flex-shrink-0">{(userLabelById[selected.user_id] || selected.username || 'system').slice(0,1).toUpperCase()}</div>
                <div className="min-w-0">
                  <h3 className="text-lg font-semibold text-sre-text truncate">{selected.action}</h3>
                  <div className="mt-1 text-xs text-sre-text-muted truncate">{formatLocal(selected.created_at)} — {userLabelById[selected.user_id] || selected.username || 'system'}</div>
                  <div className="mt-2 flex items-center gap-2">
                    {selected.details?.method && <span className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-sre-surface-variant text-sre-text-muted">{selected.details.method}</span>}
                    {selected.details?.status_code && (
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs ${Number(selected.details.status_code) >= 500 ? 'bg-red-100 text-red-800' : Number(selected.details.status_code) >= 400 ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-800'}`}>{selected.details.status_code}</span>
                    )}
                    {selected.details?.query !== undefined && <span className="text-xs text-sre-text-subtle ml-2">query: "{String(selected.details.query)}"</span>}
                  </div>
                </div>
              </div>

              <div className="flex gap-2 items-center">
                <div className="flex items-center gap-2 whitespace-nowrap">
                  <Button size="sm" variant="ghost" className="whitespace-nowrap" onClick={(e) => { e.stopPropagation(); copyText(prettyJson(selected.details || {})) }} aria-label="Copy JSON">Copy JSON</Button>
                  <Button size="sm" variant="ghost" className="whitespace-nowrap" onClick={(e) => { e.stopPropagation(); copyText((selected.resource_type || '') + (selected.resource_id ? `/${selected.resource_id}` : '')) }} aria-label="Copy resource">Copy Resource</Button>
                </div>
                <Button size="sm" onClick={() => setSelected(null)}>Close</Button>
              </div>
            </div>

            {/* Content */}
            <div className="p-6 grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="md:col-span-2 space-y-4">
                <div className="bg-sre-bg/30 border border-sre-border rounded-lg p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="text-xs text-sre-text-muted">Resource</div>
                      <div className="mt-1 text-sm font-medium break-all">{(selected.resource_type || '') + (selected.resource_id ? `/${selected.resource_id}` : '') || '-'}</div>
                    </div>
                    <div className="flex gap-2">
                      <button className="text-xs text-sre-text-muted hover:text-sre-text" onClick={(e) => { e.stopPropagation(); copyText((selected.resource_type || '') + (selected.resource_id ? `/${selected.resource_id}` : '')) }}>Copy</button>
                      {((selected.resource_type || '').toLowerCase() || '').startsWith('http') && (
                        <a className="text-xs text-sre-primary hover:underline" href={(selected.resource_type || '') + (selected.resource_id ? `/${selected.resource_id}` : '')} target="_blank" rel="noopener noreferrer">Open</a>
                      )}
                    </div>
                  </div>

                  <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div>
                      <div className="text-xs text-sre-text-muted">IP Address</div>
                      <div className="mt-1 text-sm font-medium">{selected.ip_address || '-'}</div>
                    </div>

                    <div>
                      <div className="text-xs text-sre-text-muted">Method</div>
                      <div className="mt-1 text-sm">{selected.details?.method || '-'}</div>
                    </div>

                    <div>
                      <div className="text-xs text-sre-text-muted">Status</div>
                      <div className="mt-1 text-sm">{selected.details?.status_code ?? '-'}</div>
                    </div>
                  </div>
                </div>

                <div className="bg-sre-bg/30 border border-sre-border rounded-lg p-4">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="text-xs text-sre-text-muted">Details</div>
                      <div className="mt-2 text-xs text-sre-text-muted">Full JSON payload (copy available)</div>
                    </div>
                    <div>
                      <button className="text-xs text-sre-text-muted hover:text-sre-text" onClick={(e) => { e.stopPropagation(); copyText(prettyJson(selected.details || {})) }}>Copy</button>
                    </div>
                  </div>
                  <pre className="mt-3 bg-sre-surface rounded p-3 overflow-auto text-xs max-h-80 border border-sre-border font-mono">{prettyJson(selected.details)}</pre>
                </div>
              </div>

              <div className="space-y-4">
                <div className="bg-sre-bg/30 border border-sre-border rounded-lg p-4">
                  <div className="text-xs text-sre-text-muted mb-2">Actor</div>
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-md bg-sre-primary/10 text-sre-primary flex items-center justify-center font-semibold text-sm">{(userLabelById[selected.user_id] || selected.username || 'system').slice(0,2).toUpperCase()}</div>
                    <div className="min-w-0">
                      <div className="text-sm font-medium truncate">{userLabelById[selected.user_id] || selected.username || selected.user_id || 'system'}</div>
                      <div className="text-xs text-sre-text-muted truncate">{selected.email || ''}</div>
                    </div>
                  </div>
                </div>

                <div className="bg-sre-bg/30 border border-sre-border rounded-lg p-4">
                  <div className="text-xs text-sre-text-muted mb-2">User Agent</div>
                  <div className="text-xs text-sre-text-muted font-mono break-words max-h-40 overflow-auto">{selected.user_agent || '-'}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
