`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { Button, Badge, Spinner } from './ui'

export default function IncidentCard({
  incident,
  canUpdateIncidents,
  userById,
  dropping,
  handleUnhideIncident,
  openIncidentModal,
  setIncidentModalTab
}) {
  const assigneeUser = incident.assignee ? userById[incident.assignee] : null
  const assigneeLabel = assigneeUser ? (assigneeUser.username || assigneeUser.id) : (incident.assignee || 'Unassigned')

  return (
    <div
      key={incident.id}
      draggable={canUpdateIncidents}
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = 'move'
        e.dataTransfer.setData('text/incident', String(incident.id))
        e.currentTarget.classList.add('opacity-50', 'scale-95', 'rotate-2')
      }}
      onDragEnd={(e) => { e.currentTarget.classList.remove('opacity-50', 'scale-95', 'rotate-2') }}
      className="group bg-gradient-to-br from-sre-bg to-sre-surface border border-sre-border/50 rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 cursor-move relative overflow-hidden backdrop-blur-sm"
    >
      {/* Priority indicator */}
      <div className={`h-2 w-full ${
        incident.severity === 'critical' ? 'bg-gradient-to-r from-red-500 to-red-600' :
        incident.severity === 'warning' ? 'bg-gradient-to-r from-yellow-500 to-orange-500' :
        'bg-gradient-to-r from-blue-500 to-blue-600'
      }`}></div>

      <div className="p-5">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className={`w-3 h-3 rounded-full flex-shrink-0 ${
              incident.severity === 'critical' ? 'bg-red-500 shadow-red-500/50 shadow-lg' :
              incident.severity === 'warning' ? 'bg-yellow-500 shadow-yellow-500/50 shadow-lg' :
              'bg-blue-500 shadow-blue-500/50 shadow-lg'
            }`}></div>
            <h3 className="font-semibold text-sre-text text-base leading-tight flex-1 min-w-0 truncate">
              {incident.alertName}
            </h3>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Badge
              variant={incident.status === 'resolved' ? 'success' : 'warning'}
              className="text-xs px-3 py-1.5 rounded-full font-medium shadow-sm"
            >
              {incident.status}
            </Badge>
          </div>
        </div>

        {/* Metadata */}
        <div className="space-y-3 mb-4">
          <div className="flex items-center gap-3 text-sm text-sre-text-muted">
            <div className="flex items-center gap-2">
              <span className="material-icons text-base text-sre-primary/70">schedule</span>
              <span className="font-medium">{new Date(incident.lastSeenAt).toLocaleString()}</span>
            </div>
          </div>

          <div className="flex items-center gap-3 text-sm text-sre-text-muted">
            <div className="flex items-center gap-2">
              <span className="material-icons text-base text-sre-primary/70">person</span>
              <span className="font-medium truncate min-w-0">{assigneeLabel}</span>
            </div>
          </div>

          {incident.jiraTicketKey && (
            <div className="flex items-center gap-3 text-sm text-sre-text-muted">
              <div className="flex items-center gap-2">
                <span className="material-icons text-base text-sre-primary/70">link</span>
                <span className="font-medium text-sre-primary hover:text-sre-primary/80 transition-colors truncate">{incident.jiraTicketKey}</span>
              </div>
            </div>
          )}
        </div>

        {/* Tags */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge
              variant={incident.severity === 'critical' ? 'error' : incident.severity === 'warning' ? 'warning' : 'info'}
              className="text-xs px-3 py-1.5 rounded-full font-medium shadow-sm"
            >
              <span className="material-icons text-sm mr-1">
                {incident.severity === 'critical' ? 'error' : incident.severity === 'warning' ? 'warning' : 'info'}
              </span>
              {incident.severity}
            </Badge>

            {incident.hideWhenResolved && (
              <Badge variant="ghost" className="whitespace-nowrap text-xs px-3 py-1.5 rounded-full border border-sre-border/50 bg-sre-surface/50">
                <span className="material-icons text-sm mr-1">visibility_off</span>
                Hide on resolve
              </Badge>
            )}
          </div>

          <div className="flex items-center gap-1">
            {incident.status === 'resolved' && incident.hideWhenResolved && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => handleUnhideIncident(incident.id)}
                className="opacity-0 group-hover:opacity-100 transition-all duration-200 p-2 h-8 w-8 hover:bg-sre-surface/50"
                title="Unhide incident"
              >
                <span className="material-icons text-sm">visibility</span>
              </Button>
            )}

            {/* Notes quick-open (shows notes count) */}
            <Button
              size="sm"
              variant="ghost"
              onClick={() => { openIncidentModal(incident); setIncidentModalTab('notes') }}
              className="opacity-0 group-hover:opacity-100 transition-all duration-200 p-2 h-8 w-8 hover:bg-sre-surface/50 relative"
              title="View notes"
            >
              <span className="material-icons text-sm">notes</span>
              {Array.isArray(incident.notes) && incident.notes.length > 0 && (
                <span className="absolute -top-1 -right-1 inline-flex items-center justify-center px-1.5 py-0.5 text-xs rounded-full bg-sre-primary text-white">{incident.notes.length}</span>
              )}
            </Button>

            <Button
              size="sm"
              variant="ghost"
              onClick={() => openIncidentModal(incident)}
              className="opacity-0 group-hover:opacity-100 transition-all duration-200 p-2 h-8 w-8 hover:bg-sre-surface/50"
            >
              <span className="material-icons text-sm">edit</span>
            </Button>
          </div>
        </div>

        {/* Shared groups */}
        {Array.isArray(incident.sharedGroupIds) && incident.sharedGroupIds.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {incident.sharedGroupIds.slice(0, 3).map((g) => (
              <span key={g} className="text-xs px-3 py-1.5 bg-sre-surface/70 border border-sre-border/30 rounded-full text-sre-text-muted font-medium truncate max-w-32"> {g} </span>
            ))}
            {incident.sharedGroupIds.length > 3 && (
              <span className="text-xs px-3 py-1.5 bg-sre-surface/70 border border-sre-border/30 rounded-full text-sre-text-muted font-medium">
                +{incident.sharedGroupIds.length - 3}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Drag indicator */}
      <div className="absolute top-3 left-3 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
        <span className="material-icons text-sre-text-muted/70 text-sm">drag_indicator</span>
      </div>

      {/* Loading overlay */}
      {dropping[incident.id] && (
        <div className="absolute inset-0 bg-sre-bg-card/90 backdrop-blur-md flex items-center justify-center rounded-xl border-2 border-sre-primary/30">
          <div className="flex items-center gap-3 text-sre-primary">
            <Spinner size="sm" />
            <span className="text-sm font-semibold">Updating...</span>
          </div>
        </div>
      )}
    </div>
  )
}