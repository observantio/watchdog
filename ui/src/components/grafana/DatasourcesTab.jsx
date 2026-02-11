import React, { useState, useMemo } from 'react'
import PropTypes from 'prop-types'
import { Button, Badge, Input, Select } from '../ui'

function DsFilterBar({ filters, setFilters, onSearch, onClearFilters, hasActiveFilters, meta, groups }) {
  const [showAdvanced, setShowAdvanced] = useState(false)
  
  // Count active filters
  const activeFilterCount = [
    filters.uid,
    filters.labelKey,
    filters.labelValue,
    filters.teamId,
    filters.showHidden
  ].filter(Boolean).length
  
  return (
    <div className="space-y-3">
      <div className="flex gap-2 items-center">
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="flex items-center gap-1 text-sm text-sre-primary hover:underline"
        >
          <span className="material-icons text-sm">{showAdvanced ? 'expand_less' : 'tune'}</span>
          {showAdvanced ? 'Hide filters' : 'Filters'}
          {activeFilterCount > 0 && (
            <Badge variant="primary" size="sm" className="ml-1">
              {activeFilterCount}
            </Badge>
          )}
        </button>
        {hasActiveFilters && (
          <button type="button" onClick={onClearFilters} className="text-xs text-sre-text-muted hover:text-red-500">
            Clear all
          </button>
        )}
      </div>
      {showAdvanced && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 p-6 bg-sre-bg-alt rounded-lg border border-sre-border">
          <div>
            <label className="block text-xs font-medium text-sre-text-muted mb-1">UID</label>
            <Input value={filters.uid} onChange={e => setFilters({...filters, uid: e.target.value})} placeholder="Exact UID match" className="px-1.5 py-1 text-xs rounded" />
          </div>
          <div>
            <label className="block text-xs font-medium text-sre-text-muted mb-1">Label Key</label>
            <select
              value={filters.labelKey}
              onChange={e => setFilters({...filters, labelKey: e.target.value, labelValue: ''})}
              className="w-full px-2 py-1.5 text-xs bg-sre-surface border border-sre-border rounded text-sre-text focus:outline-none focus:ring-2 focus:ring-sre-primary focus:border-transparent transition-all duration-200"
            >
              <option value="">Any</option>
              {(meta?.label_keys || []).map(k => <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-sre-text-muted mb-1">Label Value</label>
            <select
              value={filters.labelValue}
              onChange={e => setFilters({...filters, labelValue: e.target.value})}
              disabled={!filters.labelKey}
              className="w-full px-2 py-1.5 text-xs bg-sre-surface border border-sre-border rounded text-sre-text disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-sre-primary focus:border-transparent transition-all duration-200"
            >
              <option value="">Any</option>
              {(filters.labelKey && meta?.label_values?.[filters.labelKey] || []).map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-sre-text-muted mb-1">Team / Group</label>
            <select
              value={filters.teamId}
              onChange={e => setFilters({...filters, teamId: e.target.value})}
              className="w-full px-2 py-1.5 text-xs bg-sre-surface border border-sre-border rounded text-sre-text focus:outline-none focus:ring-2 focus:ring-sre-primary focus:border-transparent transition-all duration-200"
            >
              <option value="">All teams</option>
              {(groups || []).map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </div>
          <div className="col-span-2 md:col-span-4 flex items-center gap-3">
            <label className="flex items-center gap-2 text-xs text-sre-text cursor-pointer">
              <input type="checkbox" checked={filters.showHidden} onChange={e => setFilters({...filters, showHidden: e.target.checked})} className="w-3.5 h-3.5" />
              Show hidden datasources
            </label>
            <Button size="sm" onClick={onSearch} className="ml-auto">Apply Filters</Button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function DatasourcesTab({
  datasources, groups, filters, setFilters,
  onSearch, onClearFilters, hasActiveFilters, meta,
  openDatasourceEditor, onDeleteDatasource,
  onToggleHidden, onEditLabels, getDatasourceIcon
}) {
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    if (!query.trim()) return datasources
    const q = query.toLowerCase()
    return datasources.filter(ds => (
      (ds.name || '').toLowerCase().includes(q) ||
      (ds.type || '').toLowerCase().includes(q) ||
      (ds.url || '').toLowerCase().includes(q) ||
      (ds.uid || '').toLowerCase().includes(q)
    ))
  }, [datasources, query])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="material-icons text-2xl text-sre-primary">storage</span>
          <div>
            <h2 className="text-xl font-semibold text-sre-text">Datasources</h2>
            <p className="text-sm text-sre-text-muted">
              {datasources.length > 0
                ? `You've got access to ${datasources.length} datasource${datasources.length !== 1 ? 's' : ''}, start creating dashboards`
                : 'No datasources configured yet'}
            </p>
          </div>
        </div>
      </div>

      <div className="mb-4 flex gap-2">
        <form onSubmit={(e) => { e.preventDefault() }} className="flex gap-2 flex-1">
          <Input size="sm" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search datasources by name, type, URL or UID..." className="flex-1 px-2 py-0.5 text-sm" />
          <Button type="button" onClick={() => setQuery('')} size="sm">Clear</Button>
        </form>
        {datasources.length ? (
          <Button onClick={() => openDatasourceEditor()} variant="primary" size="sm">
            <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
            New Datasource
          </Button>
        ) : null}
      </div>

      <DsFilterBar
        filters={filters}
        setFilters={setFilters}
        onSearch={onSearch}
        onClearFilters={onClearFilters}
        hasActiveFilters={hasActiveFilters}
        meta={meta}
        groups={groups}
      />

      {filtered.length ? (
        <div className="space-y-4">
          {filtered.map((ds) => (
            <div
              key={ds.uid}
              className={`p-6 bg-sre-surface border-2 rounded-xl hover:border-sre-primary/50 hover:shadow-md transition-all duration-200 ${
                ds.is_hidden ? 'border-dashed border-sre-border/50 opacity-60' : 'border-sre-border'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-3">
                    <div className="p-2 rounded-lg bg-green-100 dark:bg-green-900/30">
                      <span className="text-2xl text-green-600 dark:text-green-400">{getDatasourceIcon(ds.type)}</span>
                    </div>
                    <div>
                      <h3 className="font-semibold text-sre-text text-lg flex items-center gap-2">
                        {ds.name}
                        {ds.is_hidden && (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300">Hidden</span>
                        )}
                      </h3>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                          ds.type === 'prometheus'
                            ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-200'
                            : ds.type === 'loki'
                            ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200'
                            : ds.type === 'tempo'
                            ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-200'
                            : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'
                        }`}>
                          {ds.type}
                        </span>
                        {ds.isDefault && (
                          <span className="px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200">default</span>
                        )}
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                          ds.access === 'proxy'
                            ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200'
                            : 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-200'
                        }`}>
                          {ds.access}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Labels */}
                  {ds.labels && Object.keys(ds.labels).length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      {Object.entries(ds.labels).map(([k, v]) => (
                        <span key={k} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200">
                          {k}{v ? `=${v}` : ''}
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="space-y-1 text-sm text-sre-text-muted">
                    <div className="flex items-center gap-2">
                      <span className="material-icons text-sm">link</span>
                      <span className="truncate">URL: {ds.url}</span>
                    </div>
                    <div className="text-xs font-mono">UID: {ds.uid}</div>
                  </div>
                </div>

                <div className="flex gap-1 ml-4">
                  {!ds.is_owned && (
                    <Button variant="ghost" size="sm" onClick={() => onToggleHidden(ds)} title={ds.is_hidden ? 'Unhide' : 'Hide'} className="p-2">
                      <span className="material-icons text-base">{ds.is_hidden ? 'visibility' : 'visibility_off'}</span>
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" onClick={() => onEditLabels(ds)} title="Edit labels" className="p-2">
                    <span className="material-icons text-base">label</span>
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => openDatasourceEditor(ds)} title="Edit" className="p-2">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => onDeleteDatasource(ds)} className="p-2 text-red-500 hover:text-red-600" title="Delete" disabled={ds.isDefault}>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
          <span className="material-icons text-5xl text-sre-text-muted mb-4 block">storage</span>
          <h3 className="text-xl font-semibold text-sre-text mb-2">No Datasources Configured</h3>
          <p className="text-sre-text-muted mb-6 max-w-md mx-auto">
            Add datasources to connect Grafana to your monitoring data and start creating dashboards.
          </p>
          <Button onClick={() => openDatasourceEditor()} variant="primary">Add Your First Datasource</Button>
        </div>
      )}
    </div>
  )
}

DatasourcesTab.propTypes = {
  datasources: PropTypes.arrayOf(PropTypes.object).isRequired,
  groups: PropTypes.arrayOf(PropTypes.object),
  filters: PropTypes.object,
  setFilters: PropTypes.func,
  onSearch: PropTypes.func,
  onClearFilters: PropTypes.func,
  hasActiveFilters: PropTypes.bool,
  meta: PropTypes.object,
  openDatasourceEditor: PropTypes.func.isRequired,
  onDeleteDatasource: PropTypes.func.isRequired,
  onToggleHidden: PropTypes.func,
  onEditLabels: PropTypes.func,
  getDatasourceIcon: PropTypes.func.isRequired,
}
