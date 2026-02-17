`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { Card, Input } from './ui'

export default function IncidentAssignmentTab({
  canReadUsers,
  assigneeSearch,
  setAssigneeSearch,
  activeIncident,
  activeIncidentDraft,
  setIncidentDrafts,
  filteredIncidentUsers,
  getUserLabel
}) {
  return (
    <Card className="p-4">
      <h4 className="text-sm font-semibold text-sre-text text-left mb-3 flex items-center">
        <span className="material-icons text-base mr-2">person</span>
        Assignment
      </h4>
      {canReadUsers ? (
        <div className="space-y-3">
          <Input
            value={assigneeSearch}
            onChange={(e) => setAssigneeSearch(e.target.value)}
            placeholder="Search users by name, username, or email"
          />
          <div className="max-h-36 overflow-auto border border-sre-border rounded-lg bg-sre-bg-alt">
            <button
              type="button"
              className={`w-full text-left flex items-center gap-2 min-w-0 px-3 py-2 text-sm hover:bg-sre-surface transition-colors ${
                !(activeIncidentDraft.assignee ?? activeIncident.assignee) ? 'text-sre-primary bg-sre-surface' : 'text-sre-text'
              }`}
              onClick={() => setIncidentDrafts((prev) => ({
                ...prev,
                [activeIncident.id]: { ...(prev[activeIncident.id] || {}), assignee: '' }
              }))}
            >
              <span className="material-icons text-sm flex-shrink-0">person_off</span>
              <span className="truncate min-w-0">Unassigned</span>
            </button>
            {filteredIncidentUsers.map((userItem) => {
              const selected = (activeIncidentDraft.assignee ?? activeIncident.assignee) === userItem.id
              return (
                <button
                  type="button"
                  key={userItem.id}
                  className={`w-full text-left flex items-center gap-2 min-w-0 px-3 py-2 text-sm hover:bg-sre-surface transition-colors ${selected ? 'text-sre-primary bg-sre-surface' : 'text-sre-text'}`}
                  onClick={() => setIncidentDrafts((prev) => ({
                    ...prev,
                    [activeIncident.id]: { ...(prev[activeIncident.id] || {}), assignee: userItem.id }
                  }))}
                >
                  <span className="material-icons text-sm flex-shrink-0">person</span>
                  <span className="truncate min-w-0">{getUserLabel(userItem)}</span>
                </button>
              )
            })}
            {filteredIncidentUsers.length === 0 && (
              <div className="px-3 py-2 text-xs text-sre-text-muted">No users found</div>
            )}
          </div>
        </div>
      ) : (
        <div className="text-sm text-sre-text-muted text-left p-3 bg-sre-bg-alt border border-sre-border rounded-lg">
          You do not have permission to list users. Assignee changes require read users access.
        </div>
      )}
    </Card>
  )
}