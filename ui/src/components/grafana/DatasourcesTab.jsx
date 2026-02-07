import React from 'react'
import PropTypes from 'prop-types'
import { Card, Button, Badge } from '../ui'

export default function DatasourcesTab({ datasources, openDatasourceEditor, onDeleteDatasource, getDatasourceIcon }) {
  return (
    <>
      <div className="mb-6 flex justify-end">
        <Button onClick={() => openDatasourceEditor()} variant="primary">
          <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Datasource
        </Button>
      </div>

      <Card
        title="Datasources"
        subtitle={`${datasources.length} datasource${datasources.length === 1 ? '' : 's'} configured`}
      >
        {datasources.length ? (
          <div className="space-y-3">
            {datasources.map((ds) => (
              <div
                key={ds.uid}
                className="p-4 bg-sre-bg-alt border border-sre-border rounded-lg hover:border-sre-accent/50 transition-all"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-2xl">{getDatasourceIcon(ds.type)}</span>
                      <h4 className="font-semibold text-sre-text text-lg">{ds.name}</h4>
                    </div>
                    
                    <div className="flex items-center gap-2 mb-2">
                      <Badge variant="info">{ds.type}</Badge>
                      {ds.isDefault && <Badge variant="neon">default</Badge>}
                      <Badge variant="outline">{ds.access}</Badge>
                    </div>

                    <p className="text-sm text-sre-text-muted mb-1">
                      <strong>URL:</strong> {ds.url}
                    </p>

                    {ds.uid && (
                      <p className="text-xs text-sre-text-muted font-mono">UID: {ds.uid}</p>
                    )}
                  </div>

                  <div className="flex gap-2 ml-4">
                    <Button variant="ghost" size="sm" onClick={() => openDatasourceEditor(ds)} title="Edit">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => onDeleteDatasource(ds)} className="text-red-500 hover:text-red-600" title="Delete" disabled={ds.isDefault}>
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
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
            </svg>
            <p className="text-sre-text-muted text-lg mb-4">No datasources configured</p>
            <Button onClick={() => openDatasourceEditor()} variant="primary">Add Your First Datasource</Button>
          </div>
        )}
      </Card>
    </>
  )
}

DatasourcesTab.propTypes = {
  datasources: PropTypes.arrayOf(PropTypes.object).isRequired,
  openDatasourceEditor: PropTypes.func.isRequired,
  onDeleteDatasource: PropTypes.func.isRequired,
  getDatasourceIcon: PropTypes.func.isRequired,
}
