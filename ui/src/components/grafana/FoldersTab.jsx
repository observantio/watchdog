import React from 'react'
import PropTypes from 'prop-types'
import { Card, Button, Input } from '../ui'
import { useState, useMemo } from 'react'

export default function FoldersTab({ folders, onCreateFolder, onDeleteFolder }) {
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    if (!query.trim()) return folders
    const q = query.toLowerCase()
    return folders.filter(f => (f.title || '').toLowerCase().includes(q))
  }, [folders, query])

  return (
    <>
      <div className="mb-6 flex gap-3">
        <form onSubmit={(e) => { e.preventDefault() }} className="flex gap-3 flex-1">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search folders by name..."
            className="flex-1"
          />
          <Button type="button" onClick={() => setQuery('')}>Clear</Button>
        </form>
        {folders.length ? (
          <Button onClick={onCreateFolder} variant="primary">
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Folder
          </Button>
        ) : null}
      </div>

      <Card
        title="Folders"
        subtitle={`${folders.length} folder${folders.length === 1 ? '' : 's'} available`}
      >
        {filtered.length ? (
          <div className="space-y-3">
            {filtered.map((folder) => (
              <div
                key={folder.uid}
                className="p-4 bg-sre-bg-alt border border-sre-border rounded-lg hover:border-sre-primary/30 transition-all"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <svg className="w-6 h-6 text-sre-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                    </svg>
                    <div>
                      <h4 className="font-semibold text-sre-text">{folder.title}</h4>
                      {folder.uid && (
                        <p className="text-xs text-sre-text-muted font-mono">UID: {folder.uid}</p>
                      )}
                    </div>
                  </div>

                  <Button variant="ghost" size="sm" onClick={() => onDeleteFolder(folder)} className="text-red-500 hover:text-red-600" title="Delete Folder">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <svg className="w-16 h-16 mx-auto text-sre-text-subtle mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
            <p className="text-sre-text-muted text-lg mb-4">No folders available</p>
            <Button onClick={onCreateFolder} variant="primary">Create Your First Folder</Button>
          </div>
        )}
      </Card>
    </>
  )
}

FoldersTab.propTypes = {
  folders: PropTypes.arrayOf(PropTypes.object).isRequired,
  onCreateFolder: PropTypes.func.isRequired,
  onDeleteFolder: PropTypes.func.isRequired,
}
