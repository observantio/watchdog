import React, { useState } from 'react'
import PropTypes from 'prop-types'
import { Button, Input, Badge, Select } from '../ui'

function FilterBar({ filters, setFilters, onSearch, onClearFilters, hasActiveFilters, meta, groups }) {
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
              Show hidden dashboards
            </label>
            <Button size="sm" onClick={onSearch} className="ml-auto">Apply Filters</Button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function DashboardsTab({
  dashboards, groups, query, setQuery, filters, setFilters,
  onSearch, onClearFilters, hasActiveFilters, meta,
  openDashboardEditor, onOpenGrafana, onDeleteDashboard,
  onToggleHidden, onEditLabels
}) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="material-icons text-2xl text-sre-primary">analytics</span>
          <div>
            <h2 className="text-xl font-semibold text-sre-text">Dashboards</h2>
            <p className="text-sm text-sre-text-muted">
              {dashboards.length > 0
                ? `You've got ${dashboards.length} dashboard${dashboards.length !== 1 ? 's' : ''} to view`
                : 'No dashboards created yet'}
            </p>
          </div>
        </div>
      </div>

      <div className="mb-4 flex gap-2">
        <form onSubmit={onSearch} className="flex gap-2 flex-1">
          <Input size="sm" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search dashboards by name or tag..." className="flex-1 px-2 py-0.5 text-sm" />
          <Button type="submit" size="sm">
            <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
            Search
          </Button>
        </form>
        {dashboards.length ? (
          <Button onClick={() => openDashboardEditor()} variant="primary" size="sm">
            <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
            New Dashboard
          </Button>
        ) : null}
      </div>

      <FilterBar
        filters={filters}
        setFilters={setFilters}
        onSearch={onSearch}
        onClearFilters={onClearFilters}
        hasActiveFilters={hasActiveFilters}
        meta={meta}
        groups={groups}
      />

      {dashboards.length ? (
        <div className="space-y-4">
          {dashboards.map((d) => (
            <div
              key={d.uid}
              className={`p-6 bg-sre-surface border-2 rounded-xl hover:border-sre-primary/50 hover:shadow-md transition-all duration-200 ${
                d.is_hidden ? 'border-dashed border-sre-border/50 opacity-60' : 'border-sre-border'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-3">
                    <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30">
                      <svg className="w-5 h-5 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                      </svg>
                    </div>
                    <div>
                      <h3 className="font-semibold text-sre-text text-lg flex items-center gap-2">
                        {d.title}
                        {d.is_hidden && (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300">Hidden</span>
                        )}
                      </h3>
                      {d.isStarred && <span className="text-yellow-500 text-sm">⭐ Starred</span>}
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2 mb-3">
                    {d.tags?.map((tag) => <Badge key={tag} variant="info">{tag}</Badge>)}
                    {d.folderTitle && (
                      <Badge variant="outline">
                        <svg className="inline-block w-4 h-4 mr-1 align-text-bottom" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        {d.folderTitle}
                      </Badge>
                    )}
                  </div>

                  {/* Labels */}
                  {d.labels && Object.keys(d.labels).length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      {Object.entries(d.labels).map(([k, v]) => (
                        <span key={k} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200">
                          {k}{v ? `=${v}` : ''}
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="text-sm text-sre-text-muted">
                    <span className="font-mono text-xs">UID: {d.uid}</span>
                  </div>
                </div>

                <div className="flex gap-1 ml-4">
                  {/* Toggle visibility (hidden for owners) */}
                  {!d.is_owned && (
                    <Button variant="ghost" size="sm" onClick={() => onToggleHidden(d)} title={d.is_hidden ? 'Unhide' : 'Hide'} className="p-2">
                      <span className="material-icons text-base">{d.is_hidden ? 'visibility' : 'visibility_off'}</span>
                    </Button>
                  )}

                  {/* Edit labels */}
                  <Button variant="ghost" size="sm" onClick={() => onEditLabels(d)} title="Edit labels" className="p-2">
                    <span className="material-icons text-base">label</span>
                  </Button>
                  {/* Open in Grafana */}
                  <Button variant="ghost" size="sm" onClick={() => onOpenGrafana(d.url)} title="Open in Grafana" className="p-2">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                  </Button>
                  {/* Edit */}
                  <Button variant="ghost" size="sm" onClick={() => openDashboardEditor(d)} title="Edit" className="p-2">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                  </Button>
                  {/* Delete */}
                  <Button variant="ghost" size="sm" onClick={() => onDeleteDashboard(d)} className="p-2 text-red-500 hover:text-red-600" title="Delete">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
          <span className="material-icons text-5xl text-sre-text-muted mb-4 block">analytics</span>
          <h3 className="text-xl font-semibold text-sre-text mb-2">No Dashboards Found</h3>
          <p className="text-sre-text-muted mb-6 max-w-md mx-auto">
            Create your first dashboard to start monitoring your systems and visualizing your data.
          </p>
          <Button onClick={() => openDashboardEditor()} variant="primary">Create Your First Dashboard</Button>
        </div>
      )}
    </div>
  )
}

DashboardsTab.propTypes = {
  dashboards: PropTypes.arrayOf(PropTypes.object).isRequired,
  groups: PropTypes.arrayOf(PropTypes.object),
  query: PropTypes.string.isRequired,
  setQuery: PropTypes.func.isRequired,
  filters: PropTypes.object,
  setFilters: PropTypes.func,
  onSearch: PropTypes.func.isRequired,
  onClearFilters: PropTypes.func,
  hasActiveFilters: PropTypes.bool,
  meta: PropTypes.object,
  openDashboardEditor: PropTypes.func.isRequired,
  onOpenGrafana: PropTypes.func.isRequired,
  onDeleteDashboard: PropTypes.func.isRequired,
  onToggleHidden: PropTypes.func,
  onEditLabels: PropTypes.func,
}
