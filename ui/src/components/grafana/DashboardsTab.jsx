import React from 'react'
import PropTypes from 'prop-types'
import { Card, Button, Input, Badge } from '../ui'

export default function DashboardsTab({ dashboards, query, setQuery, onSearch, openDashboardEditor, onOpenGrafana, onDeleteDashboard }) {
  return (
    <>
      <div className="mb-6 flex gap-3">
        <form onSubmit={onSearch} className="flex gap-3 flex-1">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search dashboards by name or tag..."
            className="flex-1"
          />
          <Button type="submit">
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            Search
          </Button>
        </form>
        <Button onClick={() => openDashboardEditor()} variant="primary">
          <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Dashboard
        </Button>
      </div>

      <Card
        title="Dashboards"
        subtitle={`${dashboards.length} dashboard${dashboards.length === 1 ? '' : 's'} found`}
      >
        {dashboards.length ? (
          <div className="space-y-3">
            {dashboards.map((d) => (
              <div
                key={d.uid}
                className="p-4 bg-sre-bg-alt border border-sre-border rounded-lg hover:border-sre-primary/50 transition-all group"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <svg className="w-5 h-5 text-sre-primary flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                      </svg>
                      <h4 className="font-semibold text-sre-text text-lg">{d.title}</h4>
                      {d.isStarred && (
                        <span className="text-yellow-500">⭐</span>
                      )}
                    </div>
                    
                    <div className="flex flex-wrap gap-2 mb-2">
                      {d.tags?.map((tag) => (
                        <Badge key={tag} variant="info">{tag}</Badge>
                      ))}
                      {d.folderTitle && (
                        <Badge variant="outline">
                          <svg className="inline-block w-4 h-4 mr-1 align-text-bottom" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                          {d.folderTitle}
                        </Badge>
                      )}
                    </div>

                    {d.uid && (
                      <p className="text-xs text-sre-text-muted font-mono mt-1">UID: {d.uid}</p>
                    )}
                    {d.url && (
                      <p className="text-xs text-sre-text-subtle mt-1">{d.url}</p>
                    )}
                  </div>

                  <div className="flex gap-2 ml-4">
                    <Button variant="ghost" size="sm" onClick={() => onOpenGrafana(d.url)} title="Open in Grafana">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                      </svg>
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => openDashboardEditor(d)} title="Edit">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => onDeleteDashboard(d)} className="text-red-500 hover:text-red-600" title="Delete">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <svg className="w-16 h-16 mx-auto text-sre-text-subtle mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <p className="text-sre-text-muted text-lg mb-4">No dashboards found</p>
            <Button onClick={() => openDashboardEditor()} variant="primary">Create Your First Dashboard</Button>
          </div>
        )}
      </Card>
    </>
  )
}

DashboardsTab.propTypes = {
  dashboards: PropTypes.arrayOf(PropTypes.object).isRequired,
  query: PropTypes.string.isRequired,
  setQuery: PropTypes.func.isRequired,
  onSearch: PropTypes.func.isRequired,
  openDashboardEditor: PropTypes.func.isRequired,
  onOpenGrafana: PropTypes.func.isRequired,
  onDeleteDashboard: PropTypes.func.isRequired,
}
