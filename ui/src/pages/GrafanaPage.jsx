import  { useState, useEffect, useCallback } from 'react'
import {
  searchDashboards, createDashboard, updateDashboard, deleteDashboard,
  getDatasources, createDatasource, updateDatasource, deleteDatasource,
  getFolders, createFolder, deleteFolder, getGroups,
  toggleDashboardHidden, toggleDatasourceHidden,
  getDashboardFilterMeta, getDatasourceFilterMeta, getDashboard
} from '../api'
import {  Button, Input, Modal, ConfirmDialog, Select, Checkbox } from '../components/ui'
import { useToast } from '../contexts/ToastContext'
import HelpTooltip from '../components/HelpTooltip'
import GrafanaTabs from '../components/grafana/GrafanaTabs'
import GrafanaContent from '../components/grafana/GrafanaContent'
import { useAuth } from '../contexts/AuthContext'
import { API_BASE, GRAFANA_URL, MIMIR_PROMETHEUS_URL, LOKI_BASE, TEMPO_URL, DATASOURCE_TYPES as DS_TYPES, VISIBILITY_OPTIONS, GRAFANA_REFRESH_INTERVALS } from '../utils/constants'

const DATASOURCE_TYPES = DS_TYPES
  .filter(dt => ['prometheus', 'loki', 'tempo'].includes(dt.value))
  .map(dt => {
  const icons = {
    prometheus: <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="3" y="11" width="4" height="10" rx="1" /><rect x="9" y="7" width="4" height="14" rx="1" /><rect x="15" y="3" width="4" height="18" rx="1" /></svg>,
    loki: <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M3 7h18M3 12h18M3 17h18" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>,
    tempo: <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="11" cy="11" r="6" strokeWidth="2" /><path d="M21 21l-4.3-4.3" strokeWidth="2" strokeLinecap="round" /></svg>,
  }
  return { ...dt, icon: icons[dt.value] || null }
})
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
    if (e.status === 403) return
    const msg = e.message || String(e || '')
    const lower = msg.toLowerCase()
    if (lower.includes('not found') && (lower.includes('access denied') || lower.includes('update failed'))) return
    toast.error(msg)
  }

  // Dashboard editor state
  const [showDashboardEditor, setShowDashboardEditor] = useState(false)
  const [editingDashboard, setEditingDashboard] = useState(null)
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

  // Confirm and open Grafana in a new tab (dashboard or proxy)
  function confirmOpenInGrafana() {
    const { path } = grafanaConfirmDialog || {}
    let rawPath = '/dashboards'
    if (typeof path === 'string' && path.trim()) {
      const trimmedPath = path.trim()
      if (trimmedPath.startsWith('http://') || trimmedPath.startsWith('https://')) {
        try {
          const absoluteUrl = new URL(trimmedPath)
          rawPath = `${absoluteUrl.pathname || '/'}${absoluteUrl.search || ''}${absoluteUrl.hash || ''}`
        } catch {
          rawPath = '/dashboards'
        }
      } else {
        rawPath = trimmedPath.startsWith('/') ? trimmedPath : `/${trimmedPath}`
      }
    }
    
    // Normalize: strip any /grafana prefix, ensure leading slash, fallback to dashboards
    let normalizedPath = rawPath.replace(/^\/grafana(?=\/|$)/, '') || '/dashboards'
    
    // Ensure path starts with /
    if (!normalizedPath.startsWith('/')) {
      normalizedPath = `/${normalizedPath}`
    }
    
    const token = localStorage.getItem('auth_token')

    // ALWAYS use port 8080 (the authenticated proxy) - never allow direct Grafana access
    const proxyOrigin = `${window.location.protocol}//${window.location.hostname}:8080`
    const targetPath = `/grafana${normalizedPath}`
    
    // Always use bootstrap flow to set auth cookie before redirect
    const launchUrl = token
      ? `${proxyOrigin}/grafana/bootstrap?token=${encodeURIComponent(token)}&next=${encodeURIComponent(targetPath)}`
      : `${proxyOrigin}${targetPath}`

    // Open in new tab - user will be authenticated via proxy on port 8080
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
    if (dashboard) {
      setEditingDashboard(dashboard)

      // Try to extract datasource UID from the lightweight dashboard object first
      const dsFromTemplating = dashboard?.templating?.list?.find(v => v?.type === 'datasource')?.current?.value || ''

      setDashboardForm({
        title: dashboard.title || '',
        tags: dashboard.tags?.join(', ') || '',
        folderId: dashboard.folderId || 0,
        refresh: dashboard.refresh || '30s',
        datasourceUid: dsFromTemplating || '',
        visibility: 'private',
        sharedGroupIds: [],
      })

      // If we couldn't find a datasource in the provided object, fetch the full dashboard
      if (!dsFromTemplating && dashboard?.uid) {
        (async () => {
          try {
            const full = await getDashboard(dashboard.uid).catch(() => null)
            const ds = full?.templating?.list?.find(v => v?.type === 'datasource')?.current?.value || ''
            if (ds) setDashboardForm(prev => ({ ...prev, datasourceUid: ds }))
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
    }
    setShowDashboardEditor(true)
  }

  async function saveDashboard() {
    try {
      const tags = dashboardForm.tags
        .split(',')
        .map(t => t.trim())
        .filter(Boolean)

      const selectedDatasource = datasources.find(ds => ds.uid === dashboardForm.datasourceUid)

      const payload = {
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

      const params = new URLSearchParams({ visibility: dashboardForm.visibility })
      if (dashboardForm.visibility === 'group' && dashboardForm.sharedGroupIds?.length > 0) {
        dashboardForm.sharedGroupIds.forEach(gid => params.append('shared_group_ids', gid))
      }

      if (editingDashboard) {
        payload.dashboard.uid = editingDashboard.uid
        await updateDashboard(editingDashboard.uid, payload, params.toString())
        toast.success('Dashboard updated successfully')
      } else {
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
        visibility: 'private',
        sharedGroupIds: [],
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

  useEffect(() => {
    if (editingDatasource) return
    const urlMapping = {
      prometheus: MIMIR_PROMETHEUS_URL,
      loki: LOKI_BASE,
      tempo: TEMPO_URL,
    }
    const nameMapping = {
      prometheus: 'Mimir',
      loki: 'Loki',
      tempo: 'Tempo',
    }
    const defaultUrl = urlMapping[datasourceForm.type]
    const defaultName = nameMapping[datasourceForm.type]
    setDatasourceForm(prev => ({
      ...prev,
      url: defaultUrl || prev.url,
      name: defaultName || prev.name
    }))
  }, [datasourceForm.type, editingDatasource])

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
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-sre-text mb-2 flex items-center gap-2">
          <span className="material-icons text-sre-primary text-3xl">dashboard</span>{' '}
          Grafana
        </h1>
        <p className="text-sre-text-muted">Create and manage dashboards, datasources, and folders</p>
      </div>

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

      {/* Dashboard Editor Modal */}
      <Modal
        isOpen={showDashboardEditor}
        onClose={() => setShowDashboardEditor(false)}
        closeOnOverlayClick={false}
        title={editingDashboard ? 'Edit Dashboard' : 'Create New Dashboard'}
        size="md"
        footer={
          <div className="flex gap-3 justify-end">
            <Button variant="ghost" onClick={() => setShowDashboardEditor(false)}>Cancel</Button>
            <Button variant="primary" onClick={saveDashboard} disabled={!dashboardForm.title.trim()}>
              {editingDashboard ? 'Update Dashboard' : 'Create Dashboard'}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              Dashboard Title <span className="text-red-500">*</span> <HelpTooltip text="Enter a descriptive title for your dashboard." />
            </label>
            <Input value={dashboardForm.title} onChange={(e) => setDashboardForm({ ...dashboardForm, title: e.target.value })} placeholder="My Awesome Dashboard" required />
          </div>
          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">Tags (comma-separated)</label>
            <Input value={dashboardForm.tags} onChange={(e) => setDashboardForm({ ...dashboardForm, tags: e.target.value })} placeholder="production, metrics, monitoring" />
          </div>
          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">Folder</label>
            <Select value={dashboardForm.folderId} onChange={(e) => setDashboardForm({ ...dashboardForm, folderId: e.target.value })}>
              <option value="0">General</option>
              {folders.map((folder) => (<option key={folder.id} value={folder.id}>{folder.title}</option>))}
            </Select>
          </div>
          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">Default Datasource</label>
            <Select value={dashboardForm.datasourceUid} onChange={(e) => setDashboardForm({ ...dashboardForm, datasourceUid: e.target.value })}>
              <option value="">-- None --</option>
              {datasources.map((ds) => (<option key={ds.uid} value={ds.uid}>{ds.name} ({ds.type})</option>))}
            </Select>
          </div>
          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">Auto-refresh</label>
            <Select value={dashboardForm.refresh} onChange={(e) => setDashboardForm({ ...dashboardForm, refresh: e.target.value })}>
              {GRAFANA_REFRESH_INTERVALS.map(opt => (<option key={opt.value} value={opt.value}>{opt.label}</option>))}
            </Select>
          </div>
          <div className="border-t border-sre-border pt-4">
            <label className="block text-sm font-medium text-sre-text mb-2">Visibility</label>
            <Select value={dashboardForm.visibility} onChange={(e) => setDashboardForm({ ...dashboardForm, visibility: e.target.value, sharedGroupIds: [] })}>
              {VISIBILITY_OPTIONS.map(opt => (<option key={opt.value} value={opt.value}>{opt.label}</option>))}
            </Select>
            {dashboardForm.visibility === 'group' && (
              <div className="mt-4">
                <label className="block text-sm font-medium text-sre-text mb-2">Shared Groups</label>
                <div className="space-y-2 max-h-40 overflow-y-auto border border-sre-border rounded p-3">
                  {groups.map(group => (
                    <Checkbox key={group.id} label={group.name} checked={dashboardForm.sharedGroupIds.includes(group.id)} onChange={(e) => {
                      if (e.target.checked) setDashboardForm({ ...dashboardForm, sharedGroupIds: [...dashboardForm.sharedGroupIds, group.id] })
                      else setDashboardForm({ ...dashboardForm, sharedGroupIds: dashboardForm.sharedGroupIds.filter(id => id !== group.id) })
                    }} />
                  ))}
                  {groups.length === 0 && <p className="text-sm text-sre-text-muted">No groups available</p>}
                </div>
              </div>
            )}
          </div>
        </div>
      </Modal>

      {/* Datasource Editor Modal */}
      <Modal
        isOpen={showDatasourceEditor}
        onClose={() => setShowDatasourceEditor(false)}
        closeOnOverlayClick={false}
        title={editingDatasource ? 'Edit Datasource' : 'Create New Datasource'}
        size="md"
        footer={
          <div className="flex gap-3 justify-end">
            <Button variant="ghost" onClick={() => setShowDatasourceEditor(false)}>Cancel</Button>
            <Button variant="primary" onClick={saveDatasource} disabled={!datasourceForm.name.trim() || !datasourceForm.url.trim()}>
              {editingDatasource ? 'Update Datasource' : 'Create Datasource'}
            </Button>
          </div>
        }
      >
        <div className="space-y-6">
          <div className="space-y-4">
            <div className="pb-2 border-b border-sre-border">
              <h3 className="text-sm font-semibold text-sre-text uppercase tracking-wide">Basic Information</h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-sre-text mb-2">Name <span className="text-red-500">*</span></label>
                <Input value={datasourceForm.name} onChange={(e) => setDatasourceForm({ ...datasourceForm, name: e.target.value })} placeholder={datasourceForm.type === 'prometheus' ? 'Mimir' : datasourceForm.type === 'loki' ? 'My Loki' : 'My Tempo'} required />
              </div>
              <div>
                <label className="block text-sm font-medium text-sre-text mb-2">Type <span className="text-red-500">*</span></label>
                <Select value={datasourceForm.type} onChange={(e) => setDatasourceForm({ ...datasourceForm, type: e.target.value })} disabled={!!editingDatasource}>
                  {DATASOURCE_TYPES.map((type) => (<option key={type.value} value={type.value}>{type.label}</option>))}
                </Select>
              </div>
            </div>
          </div>
          <div className="space-y-4">
            <div className="pb-2 border-b border-sre-border">
              <h3 className="text-sm font-semibold text-sre-text uppercase tracking-wide">Connection</h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-sre-text mb-2">URL <span className="text-red-500">*</span></label>
                <Input value={datasourceForm.url} onChange={(e) => setDatasourceForm({ ...datasourceForm, url: e.target.value })} placeholder={datasourceForm.type === 'prometheus' ? MIMIR_PROMETHEUS_URL : datasourceForm.type === 'loki' ? LOKI_BASE : TEMPO_URL} required />
              </div>
              <div>
                <label className="block text-sm font-medium text-sre-text mb-2">Access Mode</label>
                <Select value={datasourceForm.access} onChange={(e) => setDatasourceForm({ ...datasourceForm, access: e.target.value })}>
                  <option value="proxy">Server (Proxy)</option>
                  <option value="direct">Browser (Direct)</option>
                </Select>
              </div>
            </div>
          </div>
          {!editingDatasource && ['prometheus', 'loki', 'tempo'].includes(datasourceForm.type) && (
            <div className="space-y-4">
              <div className="pb-2 border-b border-sre-border">
                <h3 className="text-sm font-semibold text-sre-text uppercase tracking-wide">Multi-tenant Configuration</h3>
              </div>
              <div>
                <label className="block text-sm font-medium text-sre-text mb-2">API Key <span className="text-red-500">*</span></label>
                <Select value={datasourceForm.apiKeyId} onChange={(e) => setDatasourceForm({ ...datasourceForm, apiKeyId: e.target.value })} required>
                  {defaultKey && <option key={defaultKey.id} value={defaultKey.id}>Default — {defaultKey.name}</option>}
                  {(user?.api_keys || []).filter(k => !k.is_default).map((key) => (<option key={key.id} value={key.id}>{key.name}</option>))}
                </Select>
              </div>
            </div>
          )}
          <div className="space-y-4">
            <div className="pb-2 border-b border-sre-border">
              <h3 className="text-sm font-semibold text-sre-text uppercase tracking-wide">Settings</h3>
            </div>
            <div className="flex items-center gap-2">
              <input type="checkbox" id="is-default" checked={datasourceForm.isDefault} onChange={(e) => setDatasourceForm({ ...datasourceForm, isDefault: e.target.checked })} className="w-4 h-4" />
              <label htmlFor="is-default" className="text-sm text-sre-text">Set as default datasource</label>
            </div>
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">Visibility</label>
              <Select value={datasourceForm.visibility} onChange={(e) => setDatasourceForm({ ...datasourceForm, visibility: e.target.value, sharedGroupIds: [] })}>
                {VISIBILITY_OPTIONS.map(opt => (<option key={opt.value} value={opt.value}>{opt.label}</option>))}
              </Select>
            </div>
            {datasourceForm.visibility === 'group' && (
              <div>
                <label className="block text-sm font-medium text-sre-text mb-2">Shared Groups</label>
                <div className="space-y-2 max-h-40 overflow-y-auto border border-sre-border rounded p-3">
                  {groups.map(group => (
                    <Checkbox key={group.id} label={group.name} checked={datasourceForm.sharedGroupIds.includes(group.id)} onChange={(e) => {
                      if (e.target.checked) setDatasourceForm({ ...datasourceForm, sharedGroupIds: [...datasourceForm.sharedGroupIds, group.id] })
                      else setDatasourceForm({ ...datasourceForm, sharedGroupIds: datasourceForm.sharedGroupIds.filter(id => id !== group.id) })
                    }} />
                  ))}
                  {groups.length === 0 && <p className="text-sm text-sre-text-muted">No groups available</p>}
                </div>
              </div>
            )}
          </div>
        </div>
      </Modal>

      {/* Folder Creator Modal */}
      <Modal
        isOpen={showFolderCreator}
        onClose={() => { setShowFolderCreator(false); setFolderName('') }}
        title="Create New Folder"
        size="sm"
        footer={
          <div className="flex gap-3 justify-end">
            <Button variant="ghost" onClick={() => { setShowFolderCreator(false); setFolderName('') }}>Cancel</Button>
            <Button variant="primary" onClick={handleCreateFolder} disabled={!folderName.trim()}>Create Folder</Button>
          </div>
        }
      >
        <div>
          <label className="block text-sm font-medium text-sre-text mb-2">Folder Name <span className="text-red-500">*</span></label>
          <Input value={folderName} onChange={(e) => setFolderName(e.target.value)} placeholder="Production Dashboards" required autoFocus onKeyDown={(e) => { if (e.key === 'Enter' && folderName.trim()) handleCreateFolder() }} />
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        onClose={() => setConfirmDialog({ ...confirmDialog, isOpen: false })}
        onConfirm={confirmDialog.onConfirm}
        title={confirmDialog.title}
        message={confirmDialog.message}
        variant={confirmDialog.variant}
        confirmText="Delete"
        cancelText="Cancel"
      />

      <ConfirmDialog
        isOpen={grafanaConfirmDialog.isOpen}
        onClose={() => setGrafanaConfirmDialog({ isOpen: false, path: null })}
        onConfirm={confirmOpenInGrafana}
        title="Open in Grafana"
        message="This will proxy through Be Observant to get a secure, scoped, authenticated, and restricted view of what you can view and share under Grafana. If you want full admin access, please contact an admin and you can log into Grafana directly with a different username and password."
        variant="info"
        confirmText="Continue to Grafana"
        cancelText="Cancel"
      />
    </div>
  )
}
