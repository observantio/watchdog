`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

/**
 * LogViewer component for displaying log results
 * @module components/loki/LogViewer
 */
import React, { useState } from 'react'
import PropTypes from 'prop-types'
import { Card, Badge, Button } from '../ui'
import { formatRelativeTime } from '../../utils/formatters'
import { getLogLevel, copyToClipboard } from '../../utils/helpers'

/**
 * LogEntry component for individual log display
 */
function LogEntry({ log, expanded, onToggle }) {
  const logLevel = getLogLevel(log.line)
  let badgeVariant = 'default'
  if (logLevel.text === 'ERROR') {
    badgeVariant = 'error'
  } else if (logLevel.text === 'WARN') {
    badgeVariant = 'warning'
  }

  return (
    <div className="border border-sre-border rounded-lg p-4 hover:bg-sre-surface/30 transition-colors">
      <div className="flex items-start gap-3">
        <Badge variant={badgeVariant} className="flex-shrink-0">
          {logLevel.text}
        </Badge>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className="text-xs text-sre-text-muted font-mono">
              {formatRelativeTime(log.timestamp)}
            </span>
            {log.stream && Object.entries(log.stream).map(([key, value]) => (
              <Badge key={key} variant="default" className="text-[10px]">
                {key}={value}
              </Badge>
            ))}
          </div>
          <div className={`font-mono text-sm ${logLevel.color} ${expanded ? '' : 'truncate'}`}>
            {log.line}
          </div>
          {expanded && log.parsed && (
            <pre className="mt-2 text-xs bg-sre-bg-alt p-3 rounded border border-sre-border overflow-auto max-h-64">
              {JSON.stringify(log.parsed, null, 2)}
            </pre>
          )}
        </div>
        <div className="flex gap-1 flex-shrink-0">
          <button
            onClick={onToggle}
            className="p-2 hover:bg-sre-surface rounded transition-colors"
            title={expanded ? 'Collapse' : 'Expand'}
          >
            <span className="material-icons text-sm text-sre-text-muted">
              {expanded ? 'unfold_less' : 'unfold_more'}
            </span>
          </button>
          <button
            onClick={() => copyToClipboard(log.line)}
            className="p-2 hover:bg-sre-surface rounded transition-colors"
            title="Copy to clipboard"
          >
            <span className="material-icons text-sm text-sre-text-muted">content_copy</span>
          </button>
        </div>
      </div>
    </div>
  )
}

LogEntry.propTypes = {
  log: PropTypes.shape({
    timestamp: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    line: PropTypes.string,
    stream: PropTypes.object,
    parsed: PropTypes.object,
  }).isRequired,
  expanded: PropTypes.bool,
  onToggle: PropTypes.func.isRequired,
}

/**
 * LogViewer component
 * @param {object} props - Component props
 */
export default function LogViewer({ logs, searchText, onDownload }) {
  const [expandedLogs, setExpandedLogs] = useState({})

  const toggleExpand = (logKey) => {
    setExpandedLogs((prev) => ({ ...prev, [logKey]: !prev[logKey] }))
  }

  const filteredLogs = logs.filter((log) => {
    if (!searchText) return true
    return log.line.toLowerCase().includes(searchText.toLowerCase())
  })

  if (filteredLogs.length === 0) {
    return (
      <Card title="Log Results">
        <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
          <span className="material-icons text-5xl text-sre-text-muted mb-4 block">search_off</span>
          <h3 className="text-xl font-semibold text-sre-text mb-2">No Logs Found</h3>
          <p className="text-sre-text-muted mb-6 max-w-md mx-auto">
            No logs found matching your criteria
          </p>
        </div>
      </Card>
    )
  }

  return (
    <Card
      title="Log Results"
      subtitle={`Showing ${filteredLogs.length} logs`}
      action={
        <Button variant="ghost" size="sm" onClick={onDownload}>
          <span className="material-icons text-sm mr-2">download</span>{" "}
          Download
        </Button>
      }
    >
      <div className="space-y-2">
        {filteredLogs.map((log, idx) => (
          <LogEntry
            key={`${log.timestamp}-${idx}`}
            log={log}
            expanded={expandedLogs[`${log.timestamp}-${idx}`]}
            onToggle={() => toggleExpand(`${log.timestamp}-${idx}`)}
          />
        ))}
      </div>
    </Card>
  )
}

LogViewer.propTypes = {
  logs: PropTypes.arrayOf(PropTypes.object).isRequired,
  searchText: PropTypes.string,
  onDownload: PropTypes.func.isRequired,
}
