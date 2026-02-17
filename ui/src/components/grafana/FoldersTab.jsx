import PropTypes from 'prop-types'
import { Button, Input } from '../ui'
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
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="material-icons text-2xl text-sre-primary">folder</span>
            <div>
              <h2 className="text-xl font-semibold text-sre-text">Folders</h2>
              <p className="text-sm text-sre-text-muted">
                {folders.length > 0
                  ? `${folders.length} folder${folders.length !== 1 ? 's' : ''} available`
                  : 'No folders created yet, Benefit by using folders to organize your dashboards'
                }
              </p>
            </div>
          </div>
        </div>

        <div className="mb-6 flex gap-2">
          <form onSubmit={(e) => { e.preventDefault() }} className="flex gap-2 flex-1">
            <Input
              size="sm"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search folders by name..."
              className="flex-1 px-2 py-0.5 text-sm"
            />
            <Button type="button" onClick={() => setQuery('')} size="sm">Clear</Button>
          </form>
          {folders.length ? (
            <Button onClick={onCreateFolder} variant="primary" size="sm">
              <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              New Folder
            </Button>
          ) : null}
        </div>

        {filtered.length ? (
          <div className="space-y-4">
            {filtered.map((folder) => (
              <div
                key={folder.uid}
                className="p-6 bg-sre-surface border-2 border-sre-border rounded-xl hover:border-sre-primary/50 hover:shadow-md transition-all duration-200"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-yellow-100 dark:bg-yellow-900/30">
                      <svg className="w-6 h-6 text-yellow-600 dark:text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                      </svg>
                    </div>
                    <div>
                      <h3 className="font-semibold text-sre-text text-lg">{folder.title}</h3>
                      {folder.uid && (
                        <p className="text-xs text-sre-text-muted font-mono">UID: {folder.uid}</p>
                      )}
                    </div>
                  </div>

                  <Button variant="ghost" size="sm" onClick={() => onDeleteFolder(folder)} className="p-2 text-red-500 hover:text-red-600" title="Delete Folder">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
            <span className="material-icons text-5xl text-sre-text-muted mb-4 block">folder</span>
            <h3 className="text-xl font-semibold text-sre-text mb-2">No Folders Available</h3>
            <p className="text-sre-text-muted mb-6 max-w-md mx-auto">
              Organize your dashboards by creating folders to keep your monitoring setup tidy and manageable.
            </p>
            <Button onClick={onCreateFolder} variant="primary">Create Your First Folder</Button>
          </div>
        )}
      </div>
    </>
  )
}

FoldersTab.propTypes = {
  folders: PropTypes.arrayOf(PropTypes.object).isRequired,
  onCreateFolder: PropTypes.func.isRequired,
  onDeleteFolder: PropTypes.func.isRequired,
}
