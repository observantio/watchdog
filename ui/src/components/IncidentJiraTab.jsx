import { Card, Input, Select, Button, Spinner } from './ui'

export default function IncidentJiraTab({
  activeIncident,
  activeIncidentDraft,
  setIncidentDrafts,
  jiraIntegrations,
  jiraProjects,
  setJiraProjects,
  jiraIssueTypes,
  setJiraIssueTypes,
  jiraCreating,
  canUpdateIncidents,
  toast,
  listJiraProjectsByIntegration,
  loadJiraIssueTypes,
  createIncidentJira,
  loadJiraComments,
  loadData
}) {
  return (
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
    </Card>
  )
}