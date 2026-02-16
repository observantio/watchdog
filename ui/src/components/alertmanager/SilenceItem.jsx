import React from 'react'
import { Button } from '../ui'

const SilenceItem = ({ silence, onDelete }) => {

  const visibilityLabel = silence.visibility === 'tenant'
    ? 'Public'
    : silence.visibility === 'group'
      ? 'Group'
      : 'Private'

  // Prefer a human-friendly title: use the first non-empty line of the
  // silence comment (if present), otherwise fall back to the first
  // matcher's name and value, then 'Silence'.
  let heading = 'Silence'
  if (silence.comment && typeof silence.comment === 'string') {
    const firstLine = silence.comment.split('\n')[0].trim()
    if (firstLine) heading = firstLine
  }
  if (heading === 'Silence' && Array.isArray(silence.matchers) && silence.matchers.length > 0) {
    const m = silence.matchers[0]
    const name = m.name || 'label'
    const value = m.value || ''
    heading = value ? `${name}=${value}` : name
  }

  return (
    <div
      key={silence.id}
      className="p-6 bg-sre-surface border-2 border-sre-border rounded-xl hover:border-sre-primary/50 hover:shadow-md transition-all duration-200"
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-orange-100 dark:bg-orange-900/30">
              <span className="material-icons text-xl text-orange-600 dark:text-orange-400">volume_off</span>
            </div>
            <div>
              <h3 className="font-semibold text-sre-text text-lg">{heading}</h3>
              <div className="flex items-center gap-2 mt-1">
                <span className="px-2 py-1 rounded-full text-xs font-medium bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-200">
                  Silenced
                </span>
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                  silence.visibility === 'tenant'
                    ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200'
                    : silence.visibility === 'group'
                    ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200'
                    : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'
                }`}>
                  {visibilityLabel}
                </span>
              </div>
            </div>
          </div>

          {silence.comment && (
            <p className="text-sm text-sre-text-muted mb-3">{silence.comment}</p>
          )}

          <div className="space-y-2 text-sm text-sre-text-muted">
            <div className="flex items-center gap-2">
              <span className="material-icons text-sm">fingerprint</span>
              <span className="font-mono text-xs">ID: {silence.id.slice(0, 12)}...</span>
            </div>
            {silence.matchers?.length > 0 && (
              <div className="flex items-start gap-2">
                <span className="material-icons text-sm mt-0.5">filter_list</span>
                <div className="flex flex-wrap gap-1">
                  {silence.matchers.map((m) => (
                    <span
                      key={`${m.name}-${m.isEqual ? 'eq' : 'neq'}-${m.value}`}
                      className="text-xs px-2 py-1 bg-sre-bg-alt border border-sre-border rounded text-sre-text"
                    >
                      {m.name}{m.isEqual ? '=' : '!='}{m.value}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <div className="flex items-center gap-2">
              <span className="material-icons text-sm">schedule</span>
              <span>
                {new Date(silence.starts_at || silence.startsAt).toLocaleString()} → {new Date(silence.ends_at || silence.endsAt).toLocaleString()}
              </span>
            </div>
          </div>
        </div>

        <div className="flex gap-1 ml-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={e => { e.stopPropagation(); if (typeof onDelete === 'function') onDelete(silence.id) }}
            className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-900/20"
            title="Delete Silence"
          >
            <span className="material-icons text-base">delete</span>
          </Button>
        </div>
      </div>
    </div>
  )
}

export default SilenceItem