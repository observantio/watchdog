import { Card, Button, Input } from './ui'
import HelpTooltip from './HelpTooltip'

export default function IncidentNotesTab({
  activeIncident,
  activeIncidentDraft,
  setIncidentDrafts,
  canUpdateIncidents,
  handleAddNote,
  expandedNotes,
  setExpandedNotes,
  formatDateTime,
  toast,
  jiraComments,
  jiraCommentsLoading,
  syncIncidentJiraComments,
  loadData,
  loadJiraComments,
  createIncidentJiraComment,
  userById = {}
}) {
  return (
    <Card className="p-4">
      <h4 className="text-sm font-semibold text-sre-text text-left mb-3 flex items-center">
        <span className="material-icons text-base mr-2">notes</span>
        Notes
      </h4>
      <div className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">Add note</label>
          <textarea
            value={activeIncidentDraft.note ?? ''}
            onChange={(e) => setIncidentDrafts((prev) => ({
              ...prev,
              [activeIncident.id]: { ...(prev[activeIncident.id] || {}), note: e.target.value }
            }))}
            onKeyDown={(e) => {
              // Ctrl/Cmd + Enter submits the note immediately
              if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault()
                if (canUpdateIncidents) handleAddNote(activeIncident.id)
              }
            }}
            className="w-full px-3 py-2 bg-sre-bg border border-sre-border rounded text-sre-text"
            rows={3}
            placeholder="Investigation updates, mitigation notes, root cause, handover details..."
          />

          <div className="mt-2 flex items-center justify-between gap-2">
            <div className="text-xs text-sre-text-muted">Press <span className="px-1.5 py-0.5 bg-sre-surface border border-sre-border rounded">Ctrl</span> + <span className="px-1.5 py-0.5 bg-sre-surface border border-sre-border rounded">Enter</span> to add quickly</div>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => setIncidentDrafts((prev) => ({
                ...prev,
                [activeIncident.id]: { ...(prev[activeIncident.id] || {}), note: '' }
              }))}>
                Clear
                <HelpTooltip content="Clear the note draft without saving" />
              </Button>
              <Button size="sm" onClick={() => handleAddNote(activeIncident.id)} disabled={!canUpdateIncidents || !(activeIncidentDraft.note || '').trim()}>
                Add note
                <HelpTooltip content="Save the note to the incident record" />
              </Button>
            </div>
          </div>
        </div>

        {Array.isArray(activeIncident.notes) && activeIncident.notes.length > 0 && (
          <div className="p-3 border border-sre-border rounded-lg bg-sre-bg-alt">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-medium text-sre-text text-left">Recent notes</p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="text-xs text-sre-text-muted hover:text-sre-text flex items-center gap-2"
                  onClick={() => {
                    const notes = activeIncident.notes.slice().reverse().slice(0, 10)
                    const keys = notes.map(n => n.createdAt ? String(n.createdAt) : `${n.author}-${notes.indexOf(n)}`)
                    const allExpanded = keys.every(k => expandedNotes.has(k))
                    const next = new Set(expandedNotes)
                    if (allExpanded) {
                      keys.forEach(k => next.delete(k))
                    } else {
                      keys.forEach(k => next.add(k))
                    }
                    setExpandedNotes(next)
                  }}
                >
                  <span className="material-icons text-sm">unfold_more</span>
                  <span className="sr-only">Toggle expand notes</span>
                  <HelpTooltip content="Expand or collapse all note details" />
                </button>
                <button
                  type="button"
                  className="text-xs text-sre-text-muted hover:text-sre-text flex items-center gap-2"
                  onClick={async () => {
                    try {
                      const allText = activeIncident.notes.slice().reverse().slice(0, 10).map(n => `${n.author}: ${n.text}`).join('\n\n')
                      await navigator.clipboard.writeText(allText)
                      toast.success('Copied notes to clipboard')
                    } catch (e) {
                      toast.error('Copy failed')
                    }
                  }}
                >
                  <span className="material-icons text-sm">content_copy</span>
                  <span className="sr-only">Copy notes</span>
                  <HelpTooltip content="Copy all notes to clipboard" />
                </button>
              </div>
            </div>

            <div className="space-y-3 max-h-44 overflow-auto pr-2">
              {activeIncident.notes.slice().reverse().slice(0, 10).map((note, idx) => {
                const key = note.createdAt ? String(note.createdAt) : `${note.author}-${idx}`
                const noteAuthorUser = userById[note.author]
                const noteAuthorLabel = noteAuthorUser ? getUserLabel(noteAuthorUser) : (note.author || 'unknown')
                // prepare display text same as IncidentBoardPage logic
                let displayText = note.text || ''
                displayText = displayText.replace(/\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b/g, (id) => {
                  const u = userById[id]
                  return u ? getUserLabel(u) : id
                })
                displayText = displayText.replace(/^([^\s-]+)-[0-9a-f]+/, '$1')
                const collapsed = !expandedNotes.has(key)
                return (
                  <div key={`${activeIncident.id}-modal-note-${key}`} className="p-3 bg-sre-bg rounded-lg border border-sre-border flex gap-3 items-start">
                    <div className="w-8 h-8 rounded-md bg-sre-primary/10 text-sre-primary flex items-center justify-center font-semibold text-sm flex-shrink-0">
                      {String(noteAuthorLabel || '').split(' ').map(s => s[0]).slice(0,2).join('').toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-xs text-sre-text truncate">
                          <span className="font-medium text-sre-text">{noteAuthorLabel}</span>
                          <span className="text-sre-text-muted ml-2 text-xs">· {formatDateTime(note.createdAt)}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            title="Quote into reply"
                            className="text-sre-text-muted hover:text-sre-text"
                            onClick={() => setIncidentDrafts((prev) => ({
                              ...prev,
                              [activeIncident.id]: { ...(prev[activeIncident.id] || {}), note: `${prev[activeIncident.id]?.note || ''}> ${displayText}\n\n` }
                            }))}
                          >
                            <span className="material-icons text-sm">format_quote</span>
                          </button>
                          <button
                            type="button"
                            title="Copy note"
                            className="text-sre-text-muted hover:text-sre-text"
                            onClick={async () => {
                              try {
                                await navigator.clipboard.writeText(displayText)
                                toast.success('Note copied')
                              } catch (e) {
                                toast.error('Copy failed')
                              }
                            }}
                          >
                            <span className="material-icons text-sm">content_copy</span>
                          </button>
                          <button
                            type="button"
                            title={collapsed ? 'Show more' : 'Show less'}
                            className="text-sre-text-muted hover:text-sre-text"
                            onClick={() => {
                              const next = new Set(expandedNotes)
                              if (next.has(key)) next.delete(key); else next.add(key)
                              setExpandedNotes(next)
                            }}
                          >
                            <span className="material-icons text-sm">{collapsed ? 'expand_more' : 'expand_less'}</span>
                          </button>
                        </div>
                      </div>

                      <div className={`mt-2 text-sm text-sre-text-muted ${collapsed ? 'line-clamp-3' : ''}`}>
                        {displayText}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {activeIncident.jiraTicketKey && (
          <div className="p-3 border border-sre-border rounded-lg bg-sre-bg-alt space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-sre-text text-left">Jira comments</p>
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => {
                  try {
                    await syncIncidentJiraComments(activeIncident.id)
                    await loadData()
                    await loadJiraComments(activeIncident.id)
                    toast.success('Synced Jira comments to incident notes')
                  } catch (e) {
                    toast.error(e?.body?.detail || e?.message || 'Failed to sync Jira comments')
                  }
                }}
              >
                Sync
              </Button>
            </div>

            {jiraCommentsLoading ? (
              <div className="text-xs text-sre-text-muted">Loading Jira comments…</div>
            ) : (
              <div className="space-y-2 max-h-40 overflow-auto">
                {jiraComments.length === 0 ? (
                  <div className="text-xs text-sre-text-muted">No Jira comments yet.</div>
                ) : jiraComments.map((comment) => (
                  <div key={comment.id || `${comment.author}-${comment.created}`} className="text-xs text-sre-text-muted text-left">
                    <span className="font-medium text-sre-text">{comment.author}</span> · {comment.created ? formatDateTime(comment.created) : 'unknown time'}<br />
                    {comment.body}
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-center gap-2">
              <Input
                value={activeIncidentDraft.jiraComment ?? ''}
                onChange={(e) => setIncidentDrafts((prev) => ({
                  ...prev,
                  [activeIncident.id]: { ...(prev[activeIncident.id] || {}), jiraComment: e.target.value }
                }))}
                placeholder="Add Jira comment"
              />
              <Button
                size="sm"
                onClick={async () => {
                  const comment = (activeIncidentDraft.jiraComment || '').trim()
                  if (!comment) return
                  try {
                    await createIncidentJiraComment(activeIncident.id, { comment })
                    setIncidentDrafts((prev) => ({
                      ...prev,
                      [activeIncident.id]: { ...(prev[activeIncident.id] || {}), jiraComment: '' }
                    }))
                    await loadJiraComments(activeIncident.id)
                    toast.success('Jira comment added')
                  } catch (e) {
                    toast.error(e?.body?.detail || e?.message || 'Failed to add Jira comment')
                  }
                }}
              >
                Add
              </Button>
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}