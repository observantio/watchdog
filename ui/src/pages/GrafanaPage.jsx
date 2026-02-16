import  { useState, useEffect, useCallback } from 'react'
import {
  searchDashboards, createDashboard, updateDashboard, deleteDashboard,
  getDatasources, createDatasource, updateDatasource, deleteDatasource,
  getFolders, createFolder, deleteFolder, getGroups,
  toggleDashboardHidden, toggleDatasourceHidden,
  getDashboardFilterMeta, getDatasourceFilterMeta, getDashboard
} from '../api'
import { Button, Input, ConfirmDialog, Select, Checkbox } from '../components/ui'
import PageHeader from '../components/ui/PageHeader'
import DashboardEditorModal from '../components/grafana/DashboardEditorModal'
import DatasourceEditorModal from '../components/grafana/DatasourceEditorModal'
import FolderCreatorModal from '../components/grafana/FolderCreatorModal'
import { useToast } from '../contexts/ToastContext'
import HelpTooltip from '../components/HelpTooltip'
import GrafanaTabs from '../components/grafana/GrafanaTabs'
import GrafanaContent from '../components/grafana/GrafanaContent'
import { useAuth } from '../contexts/AuthContext'
import { API_BASE, GRAFANA_URL, MIMIR_PROMETHEUS_URL, LOKI_BASE, TEMPO_URL, VISIBILITY_OPTIONS, GRAFANA_REFRESH_INTERVALS, REFRESH_INTERVALS } from '../utils/constants'
import { GRAFANA_DATASOURCE_TYPES as DATASOURCE_TYPES } from '../utils/grafanaUtils'
import { buildGrafanaLaunchUrl } from '../utils/grafanaLaunchUtils'
// handlers moved into the component so they can access component state



export default function GrafanaPage() { // NOSONAR
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState('dashboards')
  const [dashboards, setDashboards] = useState([])
  const [datasources, setDatasources] = useState([])
  const [folders, setFolders] = useState([])
  const [groups, setGroups] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [dashboardMeta, setDashboardMeta] = useState({})
  const [datasourceMeta, setDatasourceMeta] = useState({})

  // Filter state
  const [filters, setFilters] = useState({
    teamId: '',
    showHidden: false,
  })

  const toast = useToast()

  function handleApiError(e) {
    if (!e) return

    // If this is an HTTP error thrown by `api.request`, let the global `api-error`
    // event (and `ToastContext`) handle showing deduplicated messages.
    if (e && typeof e.status === 'number') {
      // keep silent for auth/403 (handled elsewhere) and let global handler run
      return
    }

    // Non-HTTP/local errors: show a helpful toast
    const msg = e.message || String(e || '')
    const lower = msg.toLowerCase()
    if (lower.includes('not found') && (lower.includes('access denied') || lower.includes('update failed'))) return
    toast.error(msg)
  }

  // Dashboard editor state
  const [showDashboardEditor, setShowDashboardEditor] = useState(false)
  const [editingDashboard, setEditingDashboard] = useState(null)
  const [editorTab, setEditorTab] = useState('form') // 'form' | 'json'
  const [jsonContent, setJsonContent] = useState('')
  const [jsonError, setJsonError] = useState('')
  const [fileUploaded, setFileUploaded] = useState(false)
  const [dashboardForm, setDashboardForm] = useState({
    title: '',
    tags: '',
    folderId: 0,
    refresh: '30s',
    datasourceUid: '',
    visibility: 'private',
    sharedGroupIds: [],
  })

  // Datasource editor state
  const [showDatasourceEditor, setShowDatasourceEditor] = useState(false)
  const [editingDatasource, setEditingDatasource] = useState(null)
  const [datasourceForm, setDatasourceForm] = useState({
    name: '',
    type: 'prometheus',
    url: '',
    isDefault: false,
    access: 'proxy',
    visibility: 'private',
    sharedGroupIds: [],
    apiKeyId: '',
  })

  // Folder creator state
  const [showFolderCreator, setShowFolderCreator] = useState(false)
  const [folderName, setFolderName] = useState('')

  // Confirm dialog state
  const [confirmDialog, setConfirmDialog] = useState({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: null,
    variant: 'danger'
  })

  // Grafana access confirmation state
  const [grafanaConfirmDialog, setGrafanaConfirmDialog] = useState({
    isOpen: false,
    path: null
  })

  // Open-in Grafana: set confirmation dialog
  function openInGrafana(path) {
    setGrafanaConfirmDialog({
      isOpen: true,
      path: path
    })
  }

  function confirmOpenInGrafana() {
    const { path } = grafanaConfirmDialog || {}
    const token = localStorage.getItem('auth_token')
    const launchUrl = buildGrafanaLaunchUrl({
      path,
      token,
      protocol: window.location.protocol,
      hostname: window.location.hostname,
    })

    window.open(launchUrl, '_blank', 'noopener,noreferrer')
    setGrafanaConfirmDialog({ isOpen: false, path: null })
  }

  const defaultKey = (user?.api_keys || []).find((k) => k.is_default) || (user?.api_keys || [])[0]

  useEffect(() => {
    loadData()
    loadGroups()
  }, [activeTab])

  async function loadGroups() {
    try {
      const groupsData = await getGroups().catch(() => [])
      setGroups(groupsData)
    } catch { /* silent */ }
  }

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      if (activeTab === 'dashboards') {
        const [dashboardsData, foldersData, datasourcesData, dashboardMetaData] = await Promise.all([
          searchDashboards({
            query: query || undefined,
            teamId: filters.teamId || undefined,
            showHidden: filters.showHidden,
          }).catch(() => []),
          getFolders().catch(() => []),
          getDatasources().catch(() => []),
          getDashboardFilterMeta().catch(() => ({})),
        ])
        setDashboards(dashboardsData)
        setFolders(foldersData)
        setDatasources(datasourcesData)
        setDashboardMeta(dashboardMetaData)
      } else if (activeTab === 'datasources') {
        const [datasourcesData, datasourceMetaData] = await Promise.all([
          getDatasources({
            teamId: filters.teamId || undefined,
            showHidden: filters.showHidden,
          }).catch(() => []),
          getDatasourceFilterMeta().catch(() => ({})),
        ])
        setDatasources(datasourcesData)
        setDatasourceMeta(datasourceMetaData)
      } else if (activeTab === 'folders') {
        const foldersData = await getFolders().catch(() => [])
        setFolders(foldersData)
      }
    } catch (e) {
      handleApiError(e)
    } finally {
      setLoading(false)
    }
  }, [activeTab, query, filters])

  async function onSearch(e) {
    e.preventDefault()
    loadData()
  }

  function clearFilters() {
    setFilters({ teamId: '', showHidden: false })
    setQuery('')
  }

  // ---- Hide/Show ----
  async function handleToggleDashboardHidden(dashboard) {
    const nowHidden = !dashboard.is_hidden
    setConfirmDialog({
      isOpen: true,
      title: nowHidden ? 'Hide Dashboard' : 'Unhide Dashboard',
      message: nowHidden
        ? `Are you sure you want to hide "${dashboard.title}"? This will hide the dashboard for your account.`
        : `Are you sure you want to unhide "${dashboard.title}"? This will make the dashboard visible again for your account.`,
      variant: 'danger',
      onConfirm: async () => {
        try {
          await toggleDashboardHidden(dashboard.uid, nowHidden)
          toast.success(nowHidden ? 'Dashboard hidden' : 'Dashboard visible')
          loadData()
        } catch (e) { handleApiError(e) }
      }
    })
  }

  async function handleToggleDatasourceHidden(datasource) {
    const nowHidden = !datasource.is_hidden
    setConfirmDialog({
      isOpen: true,
      title: nowHidden ? 'Hide Datasource' : 'Unhide Datasource',
      message: nowHidden
        ? `Are you sure you want to hide "${datasource.name}"? This will hide the datasource for your account.`
        : `Are you sure you want to unhide "${datasource.name}"? This will make the datasource visible again for your account.`,
      variant: 'danger',
      onConfirm: async () => {
        try {
          await toggleDatasourceHidden(datasource.uid, nowHidden)
          toast.success(nowHidden ? 'Datasource hidden' : 'Datasource visible')
          loadData()
        } catch (e) { handleApiError(e) }
      }
    })
  }

  // ---- Dashboard CRUD ----
  function openDashboardEditor(dashboard = null) {
    setEditorTab('form')
    setJsonContent('')
    setJsonError('')
    setFileUploaded(false)

    if (dashboard) {
      setEditingDashboard(dashboard)

      // Helper: resolve a templating value (could be uid or name) to a datasource.uid
      const resolveToUid = (val) => {
        if (!val && val !== 0) return ''
        // templating current.value may be an object like { text, value } or a plain string
        const candidate = (typeof val === 'object' && val !== null) ? (val.value || val.text) : String(val)
        if (!candidate) return ''
        // direct uid match
        const byUid = datasources.find(d => String(d.uid) === String(candidate))
        if (byUid) return byUid.uid
        // match by friendly name
        const byName = datasources.find(d => String(d.name) === String(candidate))
        if (byName) return byName.uid
        return ''
      }

      // Try to extract datasource value from the lightweight dashboard object first
      const lightTemplating = dashboard?.templating || dashboard?.dashboard?.templating
      const rawDsValue = lightTemplating?.list?.find(v => v?.type === 'datasource')?.current?.value || ''
      const resolvedUid = resolveToUid(rawDsValue)

      setDashboardForm({
        title: dashboard.title || dashboard?.dashboard?.title || '',
        tags: dashboard.tags?.join(', ') || (dashboard?.dashboard?.tags || []).join(', ') || '',
        folderId: dashboard.folderId || dashboard?.dashboard?.folderId || 0,
        refresh: dashboard.refresh || (dashboard?.dashboard?.refresh) || '30s',
        datasourceUid: resolvedUid || '',
        visibility: dashboard.visibility || 'private',
        sharedGroupIds: dashboard.sharedGroupIds || dashboard.shared_group_ids || [],
      })

      // preload JSON editor with lightweight dashboard object if available, otherwise fetch full dashboard
      const lightDashboardObj = dashboard?.dashboard || dashboard
      if (lightDashboardObj) {
        try {
          setJsonContent(JSON.stringify(lightDashboardObj, null, 2))
        } catch (e) { /* ignore */ }
      }

      if (dashboard?.uid) {
        (async () => {
          try {
            const full = await getDashboard(dashboard.uid).catch(() => null)
            const templ = full?.dashboard?.templating || full?.templating
            const raw = templ?.list?.find(v => v?.type === 'datasource')?.current?.value || ''
            const uid = resolveToUid(raw)
            if (uid) setDashboardForm(prev => ({ ...prev, datasourceUid: uid }))

            // Always replace the JSON editor with the full dashboard when available
            if (full?.dashboard) {
              try {
                setJsonContent(JSON.stringify(full.dashboard, null, 2))
                setJsonError('')
                setFileUploaded(false)
              } catch (err) {
                // ignore stringify errors
              }
            }
          } catch (e) {
            /* ignore - leave datasource blank */
          }
        })()
      }
    } else {
      setEditingDashboard(null)
      setDashboardForm({
        title: '',
        tags: '',
        folderId: 0,
        refresh: '30s',
        datasourceUid: '',
        visibility: 'private',
        sharedGroupIds: [],
      })
      // default JSON template
      setJsonContent(JSON.stringify({ title: '', panels: [] }, null, 2))
    }
    setShowDashboardEditor(true)
  }

  async function saveDashboard() {
    try {
      // If JSON editor is active, prefer JSON content (supports exported Grafana JSON or raw dashboard object)
      let payload = null
      if (editorTab === 'json') {
        if (!jsonContent || !jsonContent.trim()) {
          toast.error('JSON content is empty')
          return
        }
        let parsed
        try {
          parsed = JSON.parse(jsonContent)
          setJsonError('')
        } catch (err) {
          setJsonError(err.message)
          toast.error('Invalid JSON — please fix and try again')
          return
        }

        // If user pasted an outer wrapper (e.g. { dashboard: { ... }, overwrite: true }), normalize
        if (parsed.dashboard || parsed?.meta || parsed?.orgId) {
          // If it's already the Grafana export format (has dashboard at top), use as-is
          if (parsed.dashboard) {
            payload = {
              dashboard: parsed.dashboard,
              folderId: parsed.folderId || Number.parseInt(dashboardForm.folderId, 10) || 0,
              overwrite: parsed.overwrite !== undefined ? !!parsed.overwrite : !!editingDashboard,
            }
          } else if (parsed?.meta && parsed.dashboard === undefined) {
            // Grafana search result shape — try to use parsed.dashboard if present; otherwise fall back to wrapped object
            payload = { dashboard: parsed, folderId: Number.parseInt(dashboardForm.folderId, 10) || 0, overwrite: !!editingDashboard }
          } else {
            payload = { dashboard: parsed, folderId: Number.parseInt(dashboardForm.folderId, 10) || 0, overwrite: !!editingDashboard }
          }
        } else {
          // Raw dashboard object provided — wrap it
          payload = { dashboard: parsed, folderId: Number.parseInt(dashboardForm.folderId, 10) || 0, overwrite: !!editingDashboard }
        }
      } else {
        // Form-based payload (existing behaviour)
        const tags = dashboardForm.tags
          .split(',')
          .map(t => t.trim())
          .filter(Boolean)

        const selectedDatasource = datasources.find(ds => ds.uid === dashboardForm.datasourceUid)

        payload = {
          dashboard: {
            title: dashboardForm.title,
            tags,
            refresh: dashboardForm.refresh,
            panels: [],
            timezone: 'browser',
            schemaVersion: 16,
            editable: true,
            templating: selectedDatasource
              ? {
                  list: [
                    {
                      name: 'ds_default',
                      label: 'Datasource',
                      type: 'datasource',
                      query: selectedDatasource.type,
                      current: {
                        text: selectedDatasource.name,
                        value: selectedDatasource.uid,
                      },
                    },
                  ],
                }
              : { list: [] },
          },
          folderId: Number.parseInt(dashboardForm.folderId, 10) || 0,
          overwrite: !!editingDashboard,
        }
      }

      // If JSON editor was used, allow the form-level tags/visibility to override or supplement
      if (payload && payload.dashboard) {
        const tagsFromForm = dashboardForm.tags
          .split(',')
          .map(t => t.trim())
          .filter(Boolean)
        if (tagsFromForm.length) payload.dashboard.tags = tagsFromForm
      }

      const params = new URLSearchParams({ visibility: dashboardForm.visibility })
      if (dashboardForm.visibility === 'group' && dashboardForm.sharedGroupIds?.length > 0) {
        dashboardForm.sharedGroupIds.forEach(gid => params.append('shared_group_ids', gid))
      }

      if (editingDashboard) {
        // Ensure UID is set on update payload and id is null
        if (payload.dashboard) {
          payload.dashboard.uid = editingDashboard.uid
          payload.dashboard.id = null
        }
        await updateDashboard(editingDashboard.uid, payload, params.toString())
        toast.success('Dashboard updated successfully')
      } else {
        // For creation: respect a uid provided inside the JSON by appending a short random suffix
        // This avoids collisions while preserving the author's base uid.
        if (payload.dashboard) {
          // always remove numeric id
          delete payload.dashboard.id

          if (payload.dashboard.uid) {
            // append a short alphanumeric suffix to keep the original hint but ensure uniqueness
            const suffix = Math.random().toString(36).slice(2, 8)
            payload.dashboard.uid = `${String(payload.dashboard.uid)}-${suffix}`
          } else {
            // let Grafana generate a UID if none provided
            delete payload.dashboard.uid
          }
        }

        await createDashboard(payload, params.toString())
        toast.success('Dashboard created successfully')
      }

      setShowDashboardEditor(false)
      loadData()
    } catch (e) {
      handleApiError(e)
    }
  }

  function handleDeleteDashboard(dashboard) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Dashboard',
      message: `Are you sure you want to delete "${dashboard.title}"? This action cannot be undone.`,
      variant: 'danger',
      onConfirm: async () => {
        try {
          await deleteDashboard(dashboard.uid)
          toast.success('Dashboard deleted successfully')
          loadData()
        } catch (e) { handleApiError(e) }
      }
    })
  }

  // ---- Datasource CRUD ----
  function openDatasourceEditor(datasource = null) {
    if (datasource) {
      setEditingDatasource(datasource)
      setDatasourceForm({
        name: datasource.name || '',
        type: datasource.type || 'prometheus',
        url: datasource.url || '',
        isDefault: datasource.isDefault || false,
        access: datasource.access || 'proxy',
        visibility: datasource.visibility || datasource.visibility || 'private',
        sharedGroupIds: datasource.sharedGroupIds || datasource.shared_group_ids || [],
        apiKeyId: '',
      })
    } else {
      const dk = (user?.api_keys || []).find((k) => k.is_default) || (user?.api_keys || [])[0]
      setEditingDatasource(null)
      setDatasourceForm({
        name: 'Mimir',
        type: 'prometheus',
        url: MIMIR_PROMETHEUS_URL,
        isDefault: false,
        access: 'proxy',
        visibility: 'private',
        sharedGroupIds: [],
        apiKeyId: dk?.id || '',
      })
    }
    setShowDatasourceEditor(true)
  }



  async function saveDatasource() {
    const isMultiTenantType = ['prometheus', 'loki', 'tempo'].includes(datasourceForm.type)
    if (!editingDatasource && isMultiTenantType && !datasourceForm.apiKeyId) {
      toast.error('API key is required for Prometheus, Loki, and Tempo datasources')
      return
    }

    try {
      const payload = {
        name: datasourceForm.name,
        type: datasourceForm.type,
        url: datasourceForm.url,
        access: datasourceForm.access,
        isDefault: datasourceForm.isDefault,
        jsonData: {},
      }

      if (!editingDatasource && isMultiTenantType) {
        const selectedKey = (user?.api_keys || []).find((k) => k.id === datasourceForm.apiKeyId)
        payload.org_id = selectedKey?.key || user?.org_id || 'default'
      }

      const params = new URLSearchParams({ visibility: datasourceForm.visibility })
      if (datasourceForm.visibility === 'group' && datasourceForm.sharedGroupIds?.length > 0) {
        datasourceForm.sharedGroupIds.forEach(gid => params.append('shared_group_ids', gid))
      }

      if (editingDatasource) {
        await updateDatasource(editingDatasource.uid, payload, params.toString())
        toast.success('Datasource updated successfully')
      } else {
        await createDatasource(payload, params.toString())
        toast.success('Datasource created successfully')
      }

      setShowDatasourceEditor(false)
      loadData()
    } catch (e) {
      handleApiError(e)
    }
  }

  function handleDeleteDatasource(datasource) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Datasource',
      message: `Are you sure you want to delete "${datasource.name}"? This will affect all dashboards using this datasource.`,
      variant: 'danger',
      onConfirm: async () => {
        try {
          await deleteDatasource(datasource.uid)
          toast.success('Datasource deleted successfully')
          loadData()
        } catch (e) { handleApiError(e) }
      }
    })
  }

  // ---- Folders ----
  async function handleCreateFolder() {
    if (!folderName.trim()) return
    try {
      await createFolder(folderName.trim())
      toast.success('Folder created successfully')
      setShowFolderCreator(false)
      setFolderName('')
      loadData()
    } catch (e) { handleApiError(e) }
  }

  function handleDeleteFolder(folder) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Folder',
      message: `Are you sure you want to delete "${folder.title}"? All dashboards in this folder will be moved to General.`,
      variant: 'danger',
      onConfirm: async () => {
        try {
          await deleteFolder(folder.uid)
          toast.success('Folder deleted successfully')
          loadData()
        } catch (e) { handleApiError(e) }
      }
    })
  }

  function getDatasourceIcon(type) {
    const found = DATASOURCE_TYPES.find(t => t.value === type)
    return found ? found.icon : '🔧'
  }

  const hasActiveFilters = filters.teamId || filters.showHidden

  return (
    <div className="animate-fade-in">
      <PageHeader icon="dashboard" title="Grafana" subtitle="Create and manage dashboards, datasources, and folders">
        <Button
          onClick={() => openInGrafana('/')}
          size="sm"
          className="flex items-center gap-2"
          title="Open Grafana in new tab"
        >
          <span className="material-icons text-sm">open_in_new</span>
          Open Grafana
        </Button>
      </PageHeader>

      <GrafanaTabs activeTab={activeTab} onChange={setActiveTab} />

      <GrafanaContent
        loading={loading}
        activeTab={activeTab}
        dashboards={dashboards}
        datasources={datasources}
        folders={folders}
        groups={groups}
        query={query}
        setQuery={setQuery}
        filters={filters}
        setFilters={setFilters}
        onSearch={onSearch}
        onClearFilters={clearFilters}
        hasActiveFilters={hasActiveFilters}
        dashboardMeta={dashboardMeta}
        datasourceMeta={datasourceMeta}
        openDashboardEditor={openDashboardEditor}
        onOpenGrafana={openInGrafana}
        onDeleteDashboard={handleDeleteDashboard}
        onToggleDashboardHidden={handleToggleDashboardHidden}
        openDatasourceEditor={openDatasourceEditor}
        onDeleteDatasource={handleDeleteDatasource}
        onToggleDatasourceHidden={handleToggleDatasourceHidden}
        getDatasourceIcon={getDatasourceIcon}
        onCreateFolder={() => setShowFolderCreator(true)}
        onDeleteFolder={handleDeleteFolder}
      />

      <DashboardEditorModal
        isOpen={showDashboardEditor}
        onClose={() => setShowDashboardEditor(false)}
        editingDashboard={editingDashboard}
        dashboardForm={dashboardForm}
        setDashboardForm={setDashboardForm}
        editorTab={editorTab}
        setEditorTab={setEditorTab}
        jsonContent={jsonContent}
        setJsonContent={setJsonContent}
        jsonError={jsonError}
        setJsonError={setJsonError}
        fileUploaded={fileUploaded}
        setFileUploaded={setFileUploaded}
        folders={folders}
        datasources={datasources}
        groups={groups}
        onSave={saveDashboard}
      />

      <DatasourceEditorModal
        isOpen={showDatasourceEditor}
        onClose={() => setShowDatasourceEditor(false)}
        editingDatasource={editingDatasource}
        datasourceForm={datasourceForm}
        setDatasourceForm={setDatasourceForm}
        user={user}
        groups={groups}
        onSave={saveDatasource}
      />

      <FolderCreatorModal
        isOpen={showFolderCreator}
        onClose={() => { setShowFolderCreator(false); setFolderName('') }}
        folderName={folderName}
        setFolderName={setFolderName}
        onCreate={handleCreateFolder}
      />

      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        onClose={() => setConfirmDialog({ ...confirmDialog, isOpen: false })}
        onConfirm={confirmDialog.onConfirm || (() => {})}
        title={confirmDialog.title}
        message={confirmDialog.message}
        variant={confirmDialog.variant || 'danger'}
        confirmText="Delete"
        cancelText="Cancel"
      />

      <ConfirmDialog
        isOpen={grafanaConfirmDialog.isOpen}
        onClose={() => setGrafanaConfirmDialog({ isOpen: false, path: null })}
        onConfirm={confirmOpenInGrafana}
        title="Open in Grafana"
        message="This will proxy through Be Observant to get a secure, scoped, authenticated, and restricted view of what you can view and share under Grafana. If you want full admin access, please contact an admin and you can log into Grafana directly with a different username and password."
        variant="primary"
        confirmText="Continue to Grafana"
        cancelText="Cancel"
      />
    </div>
  )
}
