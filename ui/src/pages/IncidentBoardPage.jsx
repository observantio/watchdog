import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'

import {
  getIncidents, updateIncident, getUsers, getGroups, createIncidentJira,
  listJiraProjectsByIntegration, listJiraIssueTypes, listIncidentJiraComments, createIncidentJiraComment, syncIncidentJiraComments,
  listJiraIntegrations, getAlertsByFilter,
} from '../api'
import { Card, Button, Select, Badge, Spinner, Modal, Input } from '../components/ui'
import { useToast } from '../contexts/ToastContext'
import { useAuth } from '../contexts/AuthContext'

export default function IncidentBoardPage() {
  const { user, hasPermission } = useAuth()
  const [incidents, setIncidents] = useState([])
  const [incidentDrafts, setIncidentDrafts] = useState({})
  const [expandedNotes, setExpandedNotes] = useState(new Set())
  const [incidentModalTab, setIncidentModalTab] = useState('details')
  const [incidentUsers, setIncidentUsers] = useState([])
  const [incidentVisibilityTab, setIncidentVisibilityTab] = useState('public')
  const [selectedGroup, setSelectedGroup] = useState('')
  const [groups, setGroups] = useState([])
  const [incidentModal, setIncidentModal] = useState({ isOpen: false, incident: null })
  const [dropping, setDropping] = useState({})
  const [assigneeSearch, setAssigneeSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showHiddenResolved, setShowHiddenResolved] = useState(false)
  const [jiraCreating, setJiraCreating] = useState({})
  const [jiraProjects, setJiraProjects] = useState([])
  const [jiraIntegrations, setJiraIntegrations] = useState([])
  const [jiraIssueTypes, setJiraIssueTypes] = useState([])
  const [jiraComments, setJiraComments] = useState([])
  const [jiraCommentsLoading, setJiraCommentsLoading] = useState(false)
  const { toast } = useToast()

  const canReadUsers = hasPermission('read:users') || hasPermission('manage:users')
  const canUpdateIncidents = hasPermission('update:incidents')

  useEffect(() => {
    loadData()
  }, [incidentVisibilityTab, selectedGroup])

  useEffect(() => {
    loadGroups()
  }, [])

  useEffect(() => {
    loadJiraIntegrations()
  }, [])

  async function loadJiraIntegrations() {
    try {
      const data = await listJiraIntegrations()
      const items = Array.isArray(data?.items) ? data.items : []
      setJiraIntegrations(items)
    } catch {
      setJiraIntegrations([])
    }
  }

  async function loadJiraIssueTypes(projectKey, integrationId) {
    try {
      if (!projectKey) {
        setJiraIssueTypes([])
        return
      }
      const data = await listJiraIssueTypes(projectKey, integrationId)
      setJiraIssueTypes(Array.isArray(data?.issueTypes) ? data.issueTypes : [])
    } catch {
      setJiraIssueTypes([])
    }
  }

  async function loadJiraComments(incidentId) {
    if (!incidentId) return
    setJiraCommentsLoading(true)
    try {
      const data = await listIncidentJiraComments(incidentId)
      setJiraComments(Array.isArray(data?.comments) ? data.comments : [])
    } catch {
      setJiraComments([])
    } finally {
      setJiraCommentsLoading(false)
    }
  }

  async function loadGroups() {
    try {
      const groupsData = await getGroups()
      const allGroups = Array.isArray(groupsData) ? groupsData : []
      const userGroupIds = new Set([
        ...((user?.group_ids || user?.groupIds || []).map((id) => String(id))),
        ...((Array.isArray(user?.groups) ? user.groups : []).map((group) => String(group?.id || ''))),
      ].filter(Boolean))

      const memberGroups = userGroupIds.size > 0
        ? allGroups.filter((group) => userGroupIds.has(String(group?.id || '')))
        : allGroups

      setGroups(memberGroups)

      if (selectedGroup && !memberGroups.some((group) => String(group?.id || '') === String(selectedGroup))) {
        setSelectedGroup('')
      }
    } catch (e) {
      console.error('Failed to load groups:', e)
    }
  }

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      if (showHiddenResolved) {
        const [openIncidents, resolvedIncidents, usersData] = await Promise.all([
          getIncidents(undefined, incidentVisibilityTab, incidentVisibilityTab === 'group' ? selectedGroup : undefined).catch(() => []),
          getIncidents('resolved', incidentVisibilityTab, incidentVisibilityTab === 'group' ? selectedGroup : undefined).catch(() => []),
          canReadUsers ? getUsers().catch(() => []) : Promise.resolve([])
        ])
        // merge, prefer the openIncidents entry when ids collide
        const map = new Map()
        for (const i of (resolvedIncidents || [])) map.set(i.id, i)
        for (const i of (openIncidents || [])) map.set(i.id, i)
        setIncidents(Array.from(map.values()))
        setIncidentUsers(Array.isArray(usersData) ? usersData : [])
      } else {
        const [incidentsData, usersData] = await Promise.all([
          getIncidents(undefined, incidentVisibilityTab, incidentVisibilityTab === 'group' ? selectedGroup : undefined).catch(() => []),
          canReadUsers ? getUsers().catch(() => []) : Promise.resolve([])
        ])
        setIncidents(Array.isArray(incidentsData) ? incidentsData : [])
        setIncidentUsers(Array.isArray(usersData) ? usersData : [])
      }
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setLoading(false)
    }
  }

  const incidentsByState = useMemo(() => {
    return {
      unresolved: incidents.filter((incident) => incident.status !== 'resolved'),
      unassigned: incidents.filter((incident) => incident.status !== 'resolved' && !incident.assignee),
      assigned: incidents.filter((incident) => incident.status !== 'resolved' && !!incident.assignee),
      resolved: incidents.filter((incident) => incident.status === 'resolved'),
    }
  }, [incidents])

  const userById = useMemo(() => {
    const map = {}
    for (const userItem of incidentUsers) {
      map[userItem.id] = userItem
    }
    return map
  }, [incidentUsers])

  const filteredIncidentUsers = useMemo(() => {
    const q = assigneeSearch.trim().toLowerCase()
    if (!q) return incidentUsers.slice(0, 20)
    return incidentUsers
      .filter((userItem) => {
        const haystack = [userItem.full_name, userItem.username, userItem.email, userItem.id]
        return haystack.some((h) => h?.toLowerCase().includes(q))
      })
  }, [incidentUsers, assigneeSearch])

  const getUserLabel = (userItem) => {
    if (!userItem) return 'Unknown user'
    const name = userItem.username || userItem.id
    const email = userItem.email ? ` <${userItem.email}>` : ''
    return `${name}${email}`
  }

  // Format ISO timestamp to `DD/MM/YYYY, hh:mm:ss am/pm` (consistently used for notes/comments)
  const formatDateTime = (iso) => {
    if (!iso) return 'unknown time'
    try {
      const d = new Date(iso)
      const pad = (n) => String(n).padStart(2, '0')
      const day = pad(d.getDate())
      const month = pad(d.getMonth() + 1)
      const year = d.getFullYear()
      let hours = d.getHours()
      const ampm = hours >= 12 ? 'pm' : 'am'
      hours = hours % 12 || 12
      const hh = pad(hours)
      const mm = pad(d.getMinutes())
      const ss = pad(d.getSeconds())
      return `${day}/${month}/${year}, ${hh}:${mm}:${ss} ${ampm}`
    } catch (e) {
      return String(iso)
    }
  }

  const openIncidentModal = (incident) => {
    const defaultIntegrationId = incident.jiraIntegrationId || jiraIntegrations[0]?.id || ''
    setIncidentModal({ isOpen: true, incident })
    setAssigneeSearch('')
    setExpandedNotes(new Set())
    setIncidentModalTab('details')
    setIncidentDrafts((prev) => ({
      ...prev,
      [incident.id]: {
        assignee: incident.assignee ?? '',
        status: incident.status,
        note: '',
        jiraTicketKey: incident.jiraTicketKey ?? '',
        jiraTicketUrl: incident.jiraTicketUrl ?? '',
        jiraIntegrationId: defaultIntegrationId,
        hideWhenResolved: incident.hideWhenResolved ?? false,
        // Jira create form defaults
        projectKey: prev?.[incident.id]?.projectKey || (jiraProjects[0]?.key || 'SRE'),
        issueType: prev?.[incident.id]?.issueType || 'Task',
        jiraComment: '',
      },
    }))
    if (defaultIntegrationId) {
      listJiraProjectsByIntegration(defaultIntegrationId)
        .then((data) => {
          const projects = Array.isArray(data?.projects) ? data.projects : []
          setJiraProjects(projects)
          const selectedProject = incidentDrafts?.[incident.id]?.projectKey || projects[0]?.key || 'SRE'
          loadJiraIssueTypes(selectedProject, defaultIntegrationId)
        })
        .catch(() => {
          setJiraProjects([])
          setJiraIssueTypes([])
        })
    } else {
      setJiraProjects([])
      setJiraIssueTypes([])
    }
    loadJiraComments(incident.id)
  }

  const renderIncidentCard = (incident) => {
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

  const handleDropOnColumn = async (target, e) => {
    e.preventDefault()
    try {
      const id = e.dataTransfer.getData('text/incident')
      if (!id) return
      const droppedId = id
      setDropping((prev) => ({ ...prev, [droppedId]: true }))
      const incident = incidents.find((it) => String(it.id) === String(droppedId))
      if (!incident) {
        setDropping((prev) => {
          const next = { ...prev }
          delete next[droppedId]
          return next
        })
        return
      }

      const payload = {}
      if (target === 'unassigned') {
        payload.assignee = null
        payload.status = 'open'
      } else if (target === 'assigned') {
        payload.status = 'open'
      } else if (target === 'resolved') {
        payload.status = 'resolved'
      }

      // Prevent resolving if the underlying alert is still active (client-side check).
      if (target === 'resolved' && incident && incident.fingerprint) {
        try {
          const activeAlerts = await getAlertsByFilter({ fingerprint: incident.fingerprint }, true)
          if (Array.isArray(activeAlerts) && activeAlerts.length > 0) {
            setDropping((prev) => {
              const next = { ...prev }
              delete next[droppedId]
              return next
            })
            try { toast.error('Cannot resolve: underlying alert is still active') } catch (_) {}
            return
          }
        } catch (err) {
          // If the check fails, fall back to server-side enforcement (do not block UX)
          console.warn('Alert active-check failed, will rely on server-side enforcement', err)
        }
      }

      await updateIncident(id, payload)
      setDropping((prev) => {
        const next = { ...prev }
        delete next[droppedId]
        return next
      })
      await loadData()
    } catch (err) {
      setError(err?.body?.detail || err?.message || 'Unable to update incident')
      try { toast.error(err?.body?.detail || err?.message || 'Unable to update incident') } catch (_) {}
    } finally {
      if (typeof droppedId !== 'undefined') {
        setDropping((prev) => {
          const next = { ...prev }
          delete next[droppedId]
          return next
        })
      }
    }
  }

  const handleSaveIncident = async (incident) => {
    const draft = incidentDrafts[incident.id] || {}
    const payload = {
      assignee: draft.assignee || null,
      status: draft.status || incident.status,
      note: draft.note || null,
      jiraTicketKey: draft.jiraTicketKey || null,
      jiraTicketUrl: draft.jiraTicketUrl || null,
      jiraIntegrationId: draft.jiraIntegrationId || null,
      hideWhenResolved: typeof draft.hideWhenResolved !== 'undefined' ? draft.hideWhenResolved : (incident.hideWhenResolved || false),
    }

    // Client-side pre-check: disallow resolving if underlying alert still active
    if (payload.status === 'resolved' && incident.fingerprint) {
      try {
        const activeAlerts = await getAlertsByFilter({ fingerprint: incident.fingerprint }, true)
        if (Array.isArray(activeAlerts) && activeAlerts.length > 0) {
          try { toast.error('Cannot mark resolved: underlying alert is still active') } catch (_) {}
          return
        }
      } catch (err) {
        // fallback to server-side enforcement if the check fails
        console.warn('Alert active-check failed during save, will rely on server-side enforcement', err)
      }
    }

    try {
      await updateIncident(incident.id, payload)
      setIncidentModal({ isOpen: false, incident: null })
      setAssigneeSearch('')
      setIncidentDrafts((prev) => {
        const next = { ...prev }
        delete next[incident.id]
        return next
      })
      await loadData()
    } catch (err) {
      setError(err?.body?.detail || err?.message || 'Unable to update incident')
      try { toast.error(err?.body?.detail || err?.message || 'Unable to update incident') } catch (_) {}
    }
  }

  // Quickly add a single note (does not close modal). Clears draft and refreshes notes.
  const handleAddNote = async (incidentId) => {
    const draft = incidentDrafts[incidentId] || {}
    const text = (draft.note || '').trim()
    if (!text) return

    try {
      const updated = await updateIncident(incidentId, { note: text })

      // update modal / incidents immediately with the server response
      setIncidentModal((prev) => ({ isOpen: true, incident: updated }))

      // clear the draft note
      setIncidentDrafts((prev) => ({
        ...prev,
        [incidentId]: { ...(prev[incidentId] || {}), note: '' }
      }))

      // also update incidents list optimistically
      setIncidents((prev) => prev.map((it) => (String(it.id) === String(updated.id) ? updated : it)))

      await loadJiraComments(incidentId)
      try { toast.success('Note added') } catch (_) {}
    } catch (e) {
      try { toast.error(e?.body?.detail || e?.message || 'Failed to add note') } catch (_) {}
    }
  }

  const handleUnhideIncident = async (incidentId) => {
    try {
      setDropping((prev) => ({ ...prev, [incidentId]: true }))
      await updateIncident(incidentId, { hideWhenResolved: false })
      await loadData()
      try { toast.success('Incident unhidden') } catch (_) {}
    } catch (err) {
      setError(err?.body?.detail || err?.message || 'Unable to unhide incident')
      try { toast.error(err?.body?.detail || err?.message || 'Unable to unhide incident') } catch (_) {}
    } finally {
      setDropping((prev) => {
        const next = { ...prev }
        delete next[incidentId]
        return next
      })
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-16">
        <Alert variant="error" className="max-w-md mx-auto">
          {error}
        </Alert>
      </div>
    )
  }

  const activeIncident = incidentModal.incident
  const activeIncidentDraft = activeIncident ? (incidentDrafts[activeIncident.id] || {}) : {}
  const stats = {
    totalIncidents: incidents.length,
    unresolved: incidentsByState.unresolved.length,
    unassigned: incidentsByState.unassigned.length,
  }

  return (
    <div className="min-h-screen via-sre-bg-alt to-sre-bg">
      <div className="">
        {/* Header Section */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-6">
            <div className="flex flex-col gap-4">
              <div>
                <h1 className="text-3xl font-bold text-sre-text"><span className="material-icons text-3xl text-sre-primary">assignment</span> InOps</h1>
                <p className="text-sre-text-muted mt-1">Manage and track incident response workflows</p>
              </div>

              <div className="flex items-center gap-2">
                <div className="flex items-center gap-2 p-1 bg-sre-surface rounded-lg border border-sre-border">
                  <Button
                    variant={incidentVisibilityTab === 'public' ? 'primary' : 'ghost'}
                    size="sm"
                    onClick={() => {
                      setIncidentVisibilityTab('public')
                      setSelectedGroup('')
                    }}
                    className="px-4 py-2"
                  >
                    <span className="material-icons text-sm mr-2">public</span>
                    Public
                  </Button>
                  <Button
                    variant={incidentVisibilityTab === 'private' ? 'primary' : 'ghost'}
                    size="sm"
                    onClick={() => {
                      setIncidentVisibilityTab('private')
                      setSelectedGroup('')
                    }}
                    className="px-4 py-2"
                  >
                    <span className="material-icons text-sm mr-2">lock</span>
                    Private
                  </Button>
                  <Button
                    variant={incidentVisibilityTab === 'group' ? 'primary' : 'ghost'}
                    size="sm"
                    onClick={() => setIncidentVisibilityTab('group')}
                    className="px-4 py-2"
                  >
                    <span className="material-icons text-sm mr-2">group</span>
                    Group
                  </Button>
                  {incidentVisibilityTab === 'group' && (
                    groups.length > 0 ? (
                      <Select
                        value={selectedGroup}
                        onChange={setSelectedGroup}
                        placeholder="Select group..."
                        className="w-48"
                      >
                        {groups.map((group) => (
                          <option key={group.id} value={group.id}>
                            {group.name}
                          </option>
                        ))}
                      </Select>
                    ) : (
                      <div className="truncate text-sre-text-muted text-sm px-3 py-2 bg-sre-surface border border-sre-border rounded w-48">
                        Could not fetch any groups you are in InOps
                      </div>
                    )
                  )}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-6">
              {/* Stats */}
              <div className="flex items-center gap-4 text-sm">
                <div className="flex items-center gap-2 px-3 py-2 bg-sre-surface rounded-lg border border-sre-border">
                  <span className="material-icons text-base text-orange-500">warning</span>
                  <span className="font-medium text-sre-text">{stats.unresolved}</span>
                  <span className="text-sre-text-muted">unresolved</span>
                </div>
                <div className="flex items-center gap-2 px-3 py-2 bg-sre-surface rounded-lg border border-sre-border">
                  <span className="material-icons text-base text-blue-500">person_off</span>
                  <span className="font-medium text-sre-text">{stats.unassigned}</span>
                  <span className="text-sre-text-muted">unassigned</span>
                </div>
                <div className="flex items-center gap-2 px-3 py-2 bg-sre-surface rounded-lg border border-sre-border">
                  <span className="material-icons text-base text-gray-500">assignment_turned_in</span>
                  <span className="font-medium text-sre-text">{stats.totalIncidents}</span>
                  <span className="text-sre-text-muted">total</span>
                </div>
              </div>

              {/* Show hidden resolved toggle */}
              <div className="flex items-center gap-2">
                <label className="inline-flex items-center gap-2 text-sm text-sre-text-muted">
                  <input
                    type="checkbox"
                    className="form-checkbox h-4 w-4"
                    checked={showHiddenResolved}
                    onChange={(e) => { setShowHiddenResolved(e.target.checked); loadData() }}
                  />
                  <span>Show hidden resolved</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        {/* Board */}
        {incidents.length > 0 ? (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 min-h-[600px]">
            {/* Unassigned Column */}
            <div className="flex flex-col">
              <div className="mb-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
                    <h3 className="text-lg font-semibold text-sre-text">Unassigned</h3>
                    <span className="px-2 py-1 bg-sre-surface text-sre-text-muted text-xs font-medium rounded-full border border-sre-border">
                      {incidentsByState.unassigned.length}
                    </span>
                  </div>
                </div>
                <div className="mt-2 h-1 bg-gradient-to-r from-blue-500 to-blue-400 rounded-full"></div>
              </div>
              <div
                className={`flex-1 min-h-[500px] p-4 rounded-xl border-2 border-dashed border-sre-border/50 bg-sre-surface/30 transition-all duration-200 ${
                  canUpdateIncidents ? 'hover:border-sre-primary/30 hover:bg-sre-surface/50 cursor-move' : ''
                }`}
                onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move' }}
                onDrop={(e) => { handleDropOnColumn('unassigned', e) }}
              >
                <div className="space-y-3">
                  {incidentsByState.unassigned.length > 0 ? (
                    incidentsByState.unassigned.map(renderIncidentCard)
                  ) : (
                    <div className="flex flex-col items-center justify-center py-12 text-center">
                      <span className="material-icons text-4xl text-sre-text-muted/50 mb-3">person_off</span>
                      <p className="text-sre-text-muted text-sm">No unassigned incidents</p>
                      <p className="text-sre-text-muted/70 text-xs mt-1">Drag incidents here to unassign</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Assigned Active Column */}
            <div className="flex flex-col">
              <div className="mb-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                    <h3 className="text-lg font-semibold text-sre-text">Assigned Active</h3>
                    <span className="px-2 py-1 bg-sre-surface text-sre-text-muted text-xs font-medium rounded-full border border-sre-border">
                      {incidentsByState.assigned.length}
                    </span>
                  </div>
                </div>
                <div className="mt-2 h-1 bg-gradient-to-r from-green-500 to-green-400 rounded-full"></div>
              </div>
              <div
                className={`flex-1 min-h-[500px] p-4 rounded-xl border-2 border-dashed border-sre-border/50 bg-sre-surface/30 transition-all duration-200 ${
                  canUpdateIncidents ? 'hover:border-sre-primary/30 hover:bg-sre-surface/50 cursor-move' : ''
                }`}
                onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move' }}
                onDrop={(e) => { handleDropOnColumn('assigned', e) }}
              >
                <div className="space-y-3">
                  {incidentsByState.assigned.length > 0 ? (
                    incidentsByState.assigned.map(renderIncidentCard)
                  ) : (
                    <div className="flex flex-col items-center justify-center py-12 text-center">
                      <span className="material-icons text-4xl text-sre-text-muted/50 mb-3">engineering</span>
                      <p className="text-sre-text-muted text-sm">No active incidents</p>
                      <p className="text-sre-text-muted/70 text-xs mt-1">Assigned incidents in progress</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Resolved Column */}
            <div className="flex flex-col">
              <div className="mb-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-3 h-3 bg-purple-500 rounded-full"></div>
                    <h3 className="text-lg font-semibold text-sre-text">Resolved</h3>
                    <span className="px-2 py-1 bg-sre-surface text-sre-text-muted text-xs font-medium rounded-full border border-sre-border">
                      {incidentsByState.resolved.length}
                    </span>
                  </div>
                </div>
                <div className="mt-2 h-1 bg-gradient-to-r from-purple-500 to-purple-400 rounded-full"></div>
              </div>
              <div
                className={`flex-1 min-h-[500px] p-4 rounded-xl border-2 border-dashed border-sre-border/50 bg-sre-surface/30 transition-all duration-200 ${
                  canUpdateIncidents ? 'hover:border-sre-primary/30 hover:bg-sre-surface/50 cursor-move' : ''
                }`}
                onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move' }}
                onDrop={(e) => { handleDropOnColumn('resolved', e) }}
              >
                <div className="space-y-3">
                  {incidentsByState.resolved.length > 0 ? (
                    incidentsByState.resolved.map(renderIncidentCard)
                  ) : (
                    <div className="flex flex-col items-center justify-center py-12 text-center">
                      <span className="material-icons text-4xl text-sre-text-muted/50 mb-3">check_circle</span>
                      <p className="text-sre-text-muted text-sm">No resolved incidents</p>
                      <p className="text-sre-text-muted/70 text-xs mt-1">Completed incident responses</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-20 px-6">
            <div className="p-6  mb-6">
              <span className="material-icons text-6xl text-sre-text-muted/50">assignment_turned_in</span>
            </div>
            <h3 className="text-xl font-semibold text-sre-text mb-2">No incidents found</h3>
            <p className="text-sre-text-muted text-center max-w-md">
              Incidents will appear here automatically when alerts are triggered and require attention.
            </p>
          </div>
        )}

      {activeIncident && (
        <Modal
          isOpen={incidentModal.isOpen}
          onClose={() => {
            setIncidentModal({ isOpen: false, incident: null })
            setAssigneeSearch('')
          }}
          title={`Update Incident: ${activeIncident.alertName}`}
          size="lg"
          closeOnOverlayClick={false}
        >
          <div className="space-y-6">
            <div className="mb-4">
              <div className="flex gap-2 border-b border-sre-border pb-2">
                <button type="button" onClick={() => setIncidentModalTab('details')} className={`pl-4 pr-4 py-2 text-sm flex items-center gap-2 border-b-2 transition-colors ${incidentModalTab === 'details' ? 'border-sre-primary text-sre-primary' : 'border-transparent text-sre-text-muted hover:text-sre-text'}`}>
                  <span className="material-icons text-sm">info</span>
                  Details
                </button>
                <button type="button" onClick={() => setIncidentModalTab('assignment')} className={`pl-4 pr-4 py-2 text-sm flex items-center gap-2 border-b-2 transition-colors ${incidentModalTab === 'assignment' ? 'border-sre-primary text-sre-primary' : 'border-transparent text-sre-text-muted hover:text-sre-text'}`}>
                  <span className="material-icons text-sm">person</span>
                  Assignment
                </button>
                <button type="button" onClick={() => setIncidentModalTab('jira')} className={`pl-4 pr-4 py-2 text-sm flex items-center gap-2 border-b-2 transition-colors ${incidentModalTab === 'jira' ? 'border-sre-primary text-sre-primary' : 'border-transparent text-sre-text-muted hover:text-sre-text'}`}>
                  <span className="material-icons text-sm">link</span>
                  Jira
                </button>
                <button type="button" onClick={() => setIncidentModalTab('notes')} className={`pl-4 pr-4 py-2 text-sm flex items-center gap-2 border-b-2 transition-colors ${incidentModalTab === 'notes' ? 'border-sre-primary text-sre-primary' : 'border-transparent text-sre-text-muted hover:text-sre-text'}`}>
                  <span className="material-icons text-sm">notes</span>
                  Notes
                </button>
              </div>
            </div>

            {incidentModalTab === 'details' && (
            <Card className="p-4">
              <h4 className="text-sm font-semibold text-sre-text text-left mb-3 flex items-center">
                <span className="material-icons text-base mr-2">info</span>
                Incident Details
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">Status</label>
                  <Select
                    value={activeIncidentDraft.status ?? activeIncident.status}
                    onChange={(e) => setIncidentDrafts((prev) => ({
                      ...prev,
                      [activeIncident.id]: { ...(prev[activeIncident.id] || {}), status: e.target.value }
                    }))}
                  >
                    <option value="open">Open</option>
                    <option value="resolved">Resolved</option>
                  </Select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">Visibility</label>
                  <div className="p-2 border border-sre-border rounded bg-sre-bg-alt">
                    <div className="text-sm text-sre-text">
                      {activeIncident.visibility}
                      {Array.isArray(activeIncident.sharedGroupIds) && activeIncident.sharedGroupIds.length > 0 && (
                        <span className="text-sre-text-muted ml-2 truncate">({activeIncident.sharedGroupIds.join(', ')})</span>
                      )}
                    </div>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">Behavior</label>
                  <div className="p-2 border border-sre-border rounded bg-sre-bg-alt flex items-center justify-between gap-4">
                    <div className="text-sm text-sre-text">Hide when resolved</div>
                    <div>
                      <label className="inline-flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={activeIncidentDraft.hideWhenResolved ?? activeIncident.hideWhenResolved ?? false}
                          onChange={(e) => setIncidentDrafts((prev) => ({
                            ...prev,
                            [activeIncident.id]: { ...(prev[activeIncident.id] || {}), hideWhenResolved: e.target.checked }
                          }))}
                          className="form-checkbox h-4 w-4 text-sre-primary"
                        />
                      </label>
                    </div>
                  </div>
                </div>
              </div>
            </Card>
            )}

            {incidentModalTab === 'assignment' && (
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
            )}

            {incidentModalTab === 'jira' && (
            <Card className="p-4">
              <h4 className="text-sm font-semibold text-sre-text text-left mb-3 flex items-center">
                <span className="material-icons text-base mr-2">link</span>
                Jira Integration
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Input
                  label="Jira ticket summary"
                  value={activeIncidentDraft.jiraSummary ?? ''}
                  onChange={(e) => setIncidentDrafts((prev) => ({
                    ...prev,
                    [activeIncident.id]: { ...(prev[activeIncident.id] || {}), jiraSummary: e.target.value }
                  }))}
                  placeholder="Optional: override ticket summary (defaults to incident title)"
                />
              </div>

              {jiraIntegrations.length > 0 ? (
              <div className="mt-3 grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
                <div>
                  <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">Jira integration</label>
                  <Select
                    value={activeIncidentDraft.jiraIntegrationId ?? (jiraIntegrations[0]?.id || '')}
                    onChange={async (e) => {
                      const nextIntegrationId = e.target.value
                      setIncidentDrafts((prev) => ({
                        ...prev,
                        [activeIncident.id]: { ...(prev[activeIncident.id] || {}), jiraIntegrationId: nextIntegrationId, projectKey: '' }
                      }))
                      try {
                        const projectData = await listJiraProjectsByIntegration(nextIntegrationId)
                        const projects = Array.isArray(projectData?.projects) ? projectData.projects : []
                        setJiraProjects(projects)
                        const firstProject = projects[0]?.key || ''
                        if (firstProject) {
                          setIncidentDrafts((prev) => ({
                            ...prev,
                            [activeIncident.id]: { ...(prev[activeIncident.id] || {}), jiraIntegrationId: nextIntegrationId, projectKey: firstProject }
                          }))
                          await loadJiraIssueTypes(firstProject, nextIntegrationId)
                        } else {
                          setJiraIssueTypes([])
                        }
                      } catch {
                        setJiraProjects([])
                        setJiraIssueTypes([])
                      }
                    }}
                  >
                    {jiraIntegrations.map((item) => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </Select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">Jira project</label>
                  <Select
                    value={activeIncidentDraft.projectKey ?? (jiraProjects[0]?.key || '')}
                    onChange={(e) => {
                      const nextProject = e.target.value
                      setIncidentDrafts((prev) => ({
                        ...prev,
                        [activeIncident.id]: { ...(prev[activeIncident.id] || {}), projectKey: nextProject }
                      }))
                      loadJiraIssueTypes(nextProject, activeIncidentDraft.jiraIntegrationId)
                    }}
                  >
                    {jiraProjects.length > 0 ? jiraProjects.map((project) => (
                      <option key={project.key} value={project.key}>{project.key} — {project.name}</option>
                    )) : (
                      <option value="">No projects</option>
                    )}
                  </Select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">Issue type</label>
                  <Select
                    value={activeIncidentDraft.issueType ?? 'Task'}
                    onChange={(e) => setIncidentDrafts((prev) => ({
                      ...prev,
                      [activeIncident.id]: { ...(prev[activeIncident.id] || {}), issueType: e.target.value }
                    }))}
                  >
                    {jiraIssueTypes.length > 0 ? jiraIssueTypes.map((issueType) => (
                      <option key={issueType} value={issueType}>{issueType}</option>
                    )) : (
                      <option value="Task">Task</option>
                    )}
                  </Select>
                </div>
                <div className="md:col-span-2 flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={!!jiraCreating[activeIncident.id] || !(activeIncidentDraft.jiraIntegrationId || jiraIntegrations[0]?.id)}
                    onClick={async () => {
                      // create Jira ticket using server endpoint
                      if (!canUpdateIncidents) {
                        try { toast.error('Missing update:incidents permission') } catch (_) {}
                        return
                      }
                      const draft = incidentDrafts[activeIncident.id] || {}
                      const integrationId = (draft.jiraIntegrationId || jiraIntegrations[0]?.id || '').trim()
                      const projectKey = (draft.projectKey || jiraProjects[0]?.key || '').trim()
                      const issueType = (draft.issueType || 'Task').trim()
                      const summary = (draft.jiraSummary && draft.jiraSummary.trim()) || activeIncident.alertName
                      const description = `Incident: ${activeIncident.alertName}\n\nLabels: ${JSON.stringify(activeIncident.labels || {})}\nAnnotations: ${JSON.stringify(activeIncident.annotations || {})}`
                      if (!integrationId) {
                        try { toast.error('Choose a Jira integration first') } catch (_) {}
                        return
                      }
                      if (!projectKey) {
                        try { toast.error('Choose a Jira project first') } catch (_) {}
                        return
                      }
                      try {
                        setJiraCreating((s) => ({ ...s, [activeIncident.id]: true }))
                        const updated = await createIncidentJira(activeIncident.id, { integrationId, projectKey, issueType, summary, description })
                        // update local draft and refresh
                        setIncidentDrafts((prev) => ({
                          ...prev,
                          [activeIncident.id]: { ...(prev[activeIncident.id] || {}), jiraTicketKey: updated.jiraTicketKey || '', jiraTicketUrl: updated.jiraTicketUrl || '', jiraIntegrationId: integrationId }
                        }))
                        try { toast.success(`Jira created: ${updated.jiraTicketKey}`) } catch (_) {}
                        await loadJiraComments(activeIncident.id)
                        await loadData()
                      } catch (err) {
                        try { toast.error(err?.body?.detail || err?.message || 'Failed to create Jira ticket') } catch (_) {}
                      } finally {
                        setJiraCreating((s) => ({ ...s, [activeIncident.id]: false }))
                      }
                    }}
                  >
                    {jiraCreating[activeIncident.id] ? (
                      <>
                        <Spinner size="xs" />
                        <span className="ml-2">Creating…</span>
                      </>
                    ) : (
                      'Create Jira'
                    )}
                  </Button>
                </div>
              </div>
              ) : (
                <div className="mt-3 text-xs text-sre-text-muted text-left">
                  <div className="text-left">
                    No accessible Jira integration found.{' '}
                    <a href="/integrations#integrations" target="_blank" rel="noopener noreferrer" className="text-sre-primary hover:underline">
                      Create Jira integration
                    </a>
                  </div>
                </div>
              )}
            </Card>)}

            {incidentModalTab === 'notes' && (
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
                      }))}>Clear</Button>
                      <Button size="sm" onClick={() => handleAddNote(activeIncident.id)} disabled={!canUpdateIncidents || !(activeIncidentDraft.note || '').trim()}>Add note</Button>
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
                            // expand/collapse all notes by note key
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
                        </button>
                      </div>
                    </div>

                    <div className="space-y-3 max-h-44 overflow-auto pr-2">
                      {activeIncident.notes.slice().reverse().slice(0, 10).map((note, idx) => {
                        const key = note.createdAt ? String(note.createdAt) : `${note.author}-${idx}`
                        const collapsed = !expandedNotes.has(key)
                        return (
                          <div key={`${activeIncident.id}-modal-note-${key}`} className="p-3 bg-sre-bg rounded-lg border border-sre-border flex gap-3 items-start">
                            <div className="w-8 h-8 rounded-md bg-sre-primary/10 text-sre-primary flex items-center justify-center font-semibold text-sm flex-shrink-0">
                              {String(note.author || '').split(' ').map(s => s[0]).slice(0,2).join('').toUpperCase()}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between gap-3">
                                <div className="text-xs text-sre-text truncate">
                                  <span className="font-medium text-sre-text">{note.author}</span>
                                  <span className="text-sre-text-muted ml-2 text-xs">· {formatDateTime(note.createdAt)}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <button
                                    type="button"
                                    title="Quote into reply"
                                    className="text-sre-text-muted hover:text-sre-text"
                                    onClick={() => setIncidentDrafts((prev) => ({
                                      ...prev,
                                      [activeIncident.id]: { ...(prev[activeIncident.id] || {}), note: `${prev[activeIncident.id]?.note || ''}> ${note.text}\n\n` }
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
                                        await navigator.clipboard.writeText(note.text)
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
                                {note.text}
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
                          const text = (activeIncidentDraft.jiraComment || '').trim()
                          if (!text) return
                          try {
                            await createIncidentJiraComment(activeIncident.id, { text })
                            setIncidentDrafts((prev) => ({
                              ...prev,
                              [activeIncident.id]: { ...(prev[activeIncident.id] || {}), jiraComment: '' }
                            }))
                            await loadJiraComments(activeIncident.id)
                            toast.success('Comment added to Jira')
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
            </Card>)}

            <div className="flex items-center justify-end gap-2">
              <Button
                variant="secondary"
                onClick={() => {
                  setIncidentModal({ isOpen: false, incident: null })
                  setAssigneeSearch('')
                }}
              >
                Cancel
              </Button>
              <Button
                onClick={() => handleSaveIncident(activeIncident)}
                disabled={!canUpdateIncidents}
                title={!canUpdateIncidents ? 'Missing update:incidents permission' : 'Save Changes'}
              >
                Save Changes
              </Button>
            </div>
          </div>
        </Modal>
      )}

      </div>
    </div>
  )
}