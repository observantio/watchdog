`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { Card } from '../../components/ui'
import PropTypes from 'prop-types'

export default function LogQuickFilters({ 
  labelValuesCache = {}, 
  topTerms = [], 
  onSelectLabelValue = () => {}, 
  onSelectPattern = () => {} 
}) {
  const hasLabels = Object.keys(labelValuesCache || {}).length > 0

  return (
    <Card title="Quick Filters" subtitle="Filter by labels">
      <div className="space-y-3 max-h-[30rem] overflow-y-auto pr-2 scrollbar-thin">
        {Object.entries(labelValuesCache || {}).map(([label, values]) => (
          Array.isArray(values) && values?.length > 0 && (
            <div key={label}>
              <div className="text-xs text-sre-text-muted mb-2 font-medium capitalize">{label.replaceAll('_', ' ')}</div>
              <div className="space-y-1">
                {values.map((value) => (
                  <button
                    key={`${label}-${value}`}
                    onClick={() => onSelectLabelValue(label, value)}
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

        {hasLabels && (
          <div>
            <div className="text-xs text-sre-text-muted mb-2 font-medium">Text Search</div>
            <div className="space-y-1">
              {topTerms?.length > 0 ? (
                topTerms.map((t) => (
                  <button
                    key={t.term}
                    onClick={() => onSelectPattern(t.term)}
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

        {!hasLabels && (
          <div className="text-center py-4 text-sm text-sre-text-muted">
            <span className="material-icons text-2xl mb-2 opacity-50">filter_list_off</span>
            <p>No labels available yet.</p>
            <p className="text-xs mt-1">Try running a query first.</p>
          </div>
        )}
      </div>
    </Card>
  )
}

LogQuickFilters.propTypes = {
  labelValuesCache: PropTypes.objectOf(PropTypes.arrayOf(PropTypes.string)),
  topTerms: PropTypes.arrayOf(
    PropTypes.shape({
      term: PropTypes.string.isRequired,
      count: PropTypes.number.isRequired,
      iconClass: PropTypes.string,
      icon: PropTypes.string,
    })
  ),
  onSelectLabelValue: PropTypes.func,
  onSelectPattern: PropTypes.func,
}
