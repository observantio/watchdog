import  { useState, useEffect } from 'react'
import {
  searchDashboards, createDashboard, updateDashboard, deleteDashboard,
  getDatasources, createDatasource, updateDatasource, deleteDatasource,
  getFolders, createFolder, deleteFolder, getGroups
} from '../api'
import {  Button, Input, Alert, Modal, ConfirmDialog, Select, Checkbox } from '../components/ui'
import GrafanaTabs from '../components/grafana/GrafanaTabs'
import GrafanaContent from '../components/grafana/GrafanaContent'
import { useAuth } from '../contexts/AuthContext'

const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL || 'https://localhost/grafana'

const DATASOURCE_TYPES = [
  { value: 'prometheus', label: 'Mimir (Prometheus-compatible)', icon: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <rect x="3" y="11" width="4" height="10" rx="1" />
      <rect x="9" y="7" width="4" height="14" rx="1" />
      <rect x="15" y="3" width="4" height="18" rx="1" />
    </svg>
  )},
  { value: 'loki', label: 'Loki', icon: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path d="M3 7h18M3 12h18M3 17h18" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )},
  { value: 'tempo', label: 'Tempo', icon: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <circle cx="11" cy="11" r="6" strokeWidth="2" />
      <path d="M21 21l-4.3-4.3" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )},
  { value: 'graphite', label: 'Graphite', icon: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path d="M3 3v18h18" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M7 13l4-4 4 6 4-10" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )},
  { value: 'influxdb', label: 'InfluxDB', icon: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path d="M12 2v20" strokeWidth="2" strokeLinecap="round" />
      <path d="M5 7c2 4 4 6 7 6s5-2 7-6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )},
  { value: 'elasticsearch', label: 'Elasticsearch', icon: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
      <path d="M12 2l7 4v8l-7 4-7-4V6l7-4z" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )},
]

function openInGrafana(path) {
  window.open(`${GRAFANA_URL}${path}`, '_blank', 'noopener,noreferrer')
}



export default function GrafanaPage() { // NOSONAR
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState('dashboards')
  const [dashboards, setDashboards] = useState([])
  const [datasources, setDatasources] = useState([])
  const [folders, setFolders] = useState([])
  const [groups, setGroups] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  // Centralized API error handling for this page.
  // Permission errors (403) are already shown globally via toast; avoid duplicating them here.
  function handleApiError(e) {
    if (!e) return
    if (e.status === 403) return // already shown in toast

    const msg = e.message || String(e || '')
    const lower = msg.toLowerCase()
    // Suppress Grafana 'not found / access denied / update failed' messages as toasts already show them
    if (lower.includes('not found') && (lower.includes('access denied') || lower.includes('update failed'))) return

    setError(msg)
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

  // Determine default API key for the current user
  const defaultKey = (user?.api_keys || []).find((k) => k.is_default) || (user?.api_keys || [])[0]

  useEffect(() => {
    loadData()
    loadGroups()
  }, [activeTab])

  async function loadGroups() {
    try {
      const groupsData = await getGroups().catch(() => [])
      setGroups(groupsData)
    } catch (e) {
      console.error('Failed to load groups:', e)
    }
  }

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      if (activeTab === 'dashboards') {
        const [dashboardsData, foldersData, datasourcesData] = await Promise.all([
          searchDashboards().catch(() => []),
          getFolders().catch(() => []),
          getDatasources().catch(() => []),
        ])
        setDashboards(dashboardsData)
        setFolders(foldersData)
        setDatasources(datasourcesData)
      } else if (activeTab === 'datasources') {
        const datasourcesData = await getDatasources().catch(() => [])
        setDatasources(datasourcesData)
      } else if (activeTab === 'folders') {
        const foldersData = await getFolders().catch(() => [])
        setFolders(foldersData)
      }
    } catch (e) {
      handleApiError(e)
    } finally {
      setLoading(false)
    }
  }

  async function onSearch(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await searchDashboards(query)
      setDashboards(res)
    } catch (e) {
      handleApiError(e)
    } finally {
      setLoading(false)
    }
  }

  function openDashboardEditor(dashboard = null) {
    if (dashboard) {
      setEditingDashboard(dashboard)
      setDashboardForm({
        title: dashboard.title || '',
        tags: dashboard.tags?.join(', ') || '',
        folderId: dashboard.folderId || 0,
        refresh: dashboard.refresh || '30s',
        datasourceUid: '',
        visibility: 'private',
        sharedGroupIds: [],
      })
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
    setError(null)
    setSuccess(null)
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

      // Build query params for visibility
      const params = new URLSearchParams({
        visibility: dashboardForm.visibility,
      })
      if (dashboardForm.visibility === 'group' && dashboardForm.sharedGroupIds?.length > 0) {
        dashboardForm.sharedGroupIds.forEach(gid => params.append('shared_group_ids', gid))
      }

      if (editingDashboard) {
        payload.dashboard.uid = editingDashboard.uid
        await updateDashboard(editingDashboard.uid, payload, params.toString())
        setSuccess('Dashboard updated successfully')
      } else {
        await createDashboard(payload, params.toString())
        setSuccess('Dashboard created successfully')
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
        setError(null)
        setSuccess(null)
        try {
          await deleteDashboard(dashboard.uid)
          setSuccess('Dashboard deleted successfully')
          loadData()
        } catch (e) {
          handleApiError(e)
        }
      }
    })
  }

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
      const defaultKey = (user?.api_keys || []).find((k) => k.is_default) || (user?.api_keys || [])[0]
      setEditingDatasource(null)
      setDatasourceForm({
        name: '',
        type: 'prometheus',
        url: '',
        isDefault: false,
        access: 'proxy',
        visibility: 'private',
        sharedGroupIds: [],
        apiKeyId: defaultKey?.id || '',
      })
    }
    setShowDatasourceEditor(true)
  }

  async function saveDatasource() {
    setError(null)
    setSuccess(null)
    
    // Validate org_id for multi-tenant datasources
    const isMultiTenantType = ['prometheus', 'loki', 'tempo'].includes(datasourceForm.type)
    if (!editingDatasource && isMultiTenantType && !datasourceForm.apiKeyId) {
      setError('API key is required for Prometheus, Loki, and Tempo datasources')
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
      
      // Add org_id to payload for new multi-tenant datasources
      if (!editingDatasource && isMultiTenantType) {
        const selectedKey = (user?.api_keys || []).find((k) => k.id === datasourceForm.apiKeyId)
        payload.org_id = selectedKey?.key || user?.org_id || 'default'
      }

      // Build query params for visibility
      const params = new URLSearchParams({
        visibility: datasourceForm.visibility,
      })
      if (datasourceForm.visibility === 'group' && datasourceForm.sharedGroupIds?.length > 0) {
        datasourceForm.sharedGroupIds.forEach(gid => params.append('shared_group_ids', gid))
      }

      if (editingDatasource) {
        await updateDatasource(editingDatasource.uid, payload, params.toString())
        setSuccess('Datasource updated successfully')
      } else {
        await createDatasource(payload, params.toString())
        setSuccess('Datasource created successfully')
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
        setError(null)
        setSuccess(null)
        try {
          await deleteDatasource(datasource.uid)
          setSuccess('Datasource deleted successfully')
          loadData()
        } catch (e) {
          handleApiError(e)
        }
      }
    })
  }

  async function handleCreateFolder() {
    if (!folderName.trim()) return
    
    setError(null)
    setSuccess(null)
    try {
      await createFolder(folderName.trim())
      setSuccess('Folder created successfully')
      setShowFolderCreator(false)
      setFolderName('')
      loadData()
    } catch (e) {
      handleApiError(e)
    }
  }

  function handleDeleteFolder(folder) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Folder',
      message: `Are you sure you want to delete "${folder.title}"? All dashboards in this folder will be moved to General.`,
      variant: 'danger',
      onConfirm: async () => {
        setError(null)
        setSuccess(null)
        try {
          await deleteFolder(folder.uid)
          setSuccess('Folder deleted successfully')
          loadData()
        } catch (e) {
          handleApiError(e)
        }
      }
    })
  }

  function getDatasourceIcon(type) {
    const found = DATASOURCE_TYPES.find(t => t.value === type)
    return found ? found.icon : '🔧'
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-3xl font-bold text-sre-text mb-2"><span className="material-icons text-blue-600 text-3xl align-middle">analytics</span> Grafana Manager</h1>
            <p className="text-sre-text-muted">Manage dashboards, datasources, and folders with powerful SRE tooling</p>
          </div>
        </div>
        <Button
          onClick={() => openInGrafana('/')}
          variant="outline"
          className="flex items-center gap-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
          Open Grafana
        </Button>
      </div>

      {error && (
        <Alert variant="error" className="mb-6" onClose={() => setError(null)}>
          <strong>Error:</strong> {error}
        </Alert>
      )}

      {success && (
        <Alert variant="success" className="mb-6" onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      <GrafanaTabs activeTab={activeTab} onChange={setActiveTab} />

      <GrafanaContent
        loading={loading}
        activeTab={activeTab}
        dashboards={dashboards}
        datasources={datasources}
        folders={folders}
        query={query}
        setQuery={setQuery}
        onSearch={onSearch}
        openDashboardEditor={openDashboardEditor}
        onOpenGrafana={openInGrafana}
        onDeleteDashboard={handleDeleteDashboard}
        openDatasourceEditor={openDatasourceEditor}
        onDeleteDatasource={handleDeleteDatasource}
        getDatasourceIcon={getDatasourceIcon}
        onCreateFolder={() => setShowFolderCreator(true)}
        onDeleteFolder={handleDeleteFolder}
      />

      {/* Dashboard Editor Modal */}
      <Modal
        isOpen={showDashboardEditor}
        onClose={() => setShowDashboardEditor(false)}
        title={editingDashboard ? 'Edit Dashboard' : 'Create New Dashboard'}
        size="md"
        footer={
          <div className="flex gap-3 justify-end">
            <Button
              variant="ghost"
              onClick={() => setShowDashboardEditor(false)}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={saveDashboard}
              disabled={!dashboardForm.title.trim()}
            >
              {editingDashboard ? 'Update Dashboard' : 'Create Dashboard'}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <Input
            label="Dashboard Title *"
            value={dashboardForm.title}
            onChange={(e) => setDashboardForm({ ...dashboardForm, title: e.target.value })}
            placeholder="My Awesome Dashboard"
            required
          />

          <Input
            label="Tags (comma-separated)"
            value={dashboardForm.tags}
            onChange={(e) => setDashboardForm({ ...dashboardForm, tags: e.target.value })}
            placeholder="production, metrics, monitoring"
            helperText="Use tags to categorize and filter dashboards"
          />

          <Select
            label="Folder"
            value={dashboardForm.folderId}
            onChange={(e) => setDashboardForm({ ...dashboardForm, folderId: e.target.value })}
          >
            <option value="0">General</option>
            {folders.map((folder) => (
              <option key={folder.id} value={folder.id}>
                {folder.title}
              </option>
            ))}
          </Select>

          <Select
            label="Default Datasource"
            value={dashboardForm.datasourceUid}
            onChange={(e) => setDashboardForm({ ...dashboardForm, datasourceUid: e.target.value })}
            helperText="Optional: Sets the default datasource variable for this dashboard"
          >
            <option value="">-- None --</option>
            {datasources.map((ds) => (
              <option key={ds.uid} value={ds.uid}>
                {ds.name} ({ds.type})
              </option>
            ))}
          </Select>

          <Select
            label="Auto-refresh Interval"
            value={dashboardForm.refresh}
            onChange={(e) => setDashboardForm({ ...dashboardForm, refresh: e.target.value })}
            helperText="How often the dashboard should automatically refresh"
          >
            <option value="">No auto-refresh</option>
            <option value="5s">5 seconds</option>
            <option value="10s">10 seconds</option>
            <option value="30s">30 seconds</option>
            <option value="1m">1 minute</option>
            <option value="5m">5 minutes</option>
            <option value="15m">15 minutes</option>
            <option value="30m">30 minutes</option>
            <option value="1h">1 hour</option>
          </Select>

          <div className="border-t border-sre-border pt-4">
            <Select
              label="Visibility"
              value={dashboardForm.visibility}
              onChange={(e) => {
                setDashboardForm({ ...dashboardForm, visibility: e.target.value, sharedGroupIds: [] })
              }}
              helperText="Control who can access this dashboard"
            >
              <option value="private">Private (Only me)</option>
              <option value="group">Shared with Groups</option>
              <option value="tenant">Tenant-wide (Everyone in organization)</option>
            </Select>

            {dashboardForm.visibility === 'group' && (
              <div className="mt-4">
                <label htmlFor="shared-groups" className="block text-sm font-medium text-sre-text mb-2">
                  Shared Groups
                </label>
                <div id="shared-groups" className="space-y-2 max-h-40 overflow-y-auto border border-sre-border rounded p-3">
                  {groups.map(group => (
                    <Checkbox
                      key={group.id}
                      label={group.name}
                      checked={dashboardForm.sharedGroupIds.includes(group.id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setDashboardForm({
                            ...dashboardForm,
                            sharedGroupIds: [...dashboardForm.sharedGroupIds, group.id]
                          })
                        } else {
                          setDashboardForm({
                            ...dashboardForm,
                            sharedGroupIds: dashboardForm.sharedGroupIds.filter(id => id !== group.id)
                          })
                        }
                      }}
                    />
                  ))}
                  {groups.length === 0 && (
                    <p className="text-sm text-sre-text-muted">No groups available</p>
                  )}
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
        title={editingDatasource ? 'Edit Datasource' : 'Create New Datasource'}
        size="md"
        footer={
          <div className="flex gap-3 justify-end">
            <Button
              variant="ghost"
              onClick={() => setShowDatasourceEditor(false)}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={saveDatasource}
              disabled={!datasourceForm.name.trim() || !datasourceForm.url.trim()}
            >
              {editingDatasource ? 'Update Datasource' : 'Create Datasource'}
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <Input
            label="Datasource Name *"
            value={datasourceForm.name}
            onChange={(e) => setDatasourceForm({ ...datasourceForm, name: e.target.value })}
            placeholder="My Mimir"
            required
          />

          <Select
            label="Type *"
            value={datasourceForm.type}
            onChange={(e) => setDatasourceForm({ ...datasourceForm, type: e.target.value })}
            disabled={!!editingDatasource}
            helperText={editingDatasource ? "Type cannot be changed after creation" : "Select the datasource type"}
          >
            {DATASOURCE_TYPES.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </Select>

          <Input
            label="URL *"
            value={datasourceForm.url}
            onChange={(e) => setDatasourceForm({ ...datasourceForm, url: e.target.value })}
            placeholder="http://mimir:9009/prometheus"
            helperText="The URL where the datasource is accessible"
            required
          />

          <Select
            label="Access Mode"
            value={datasourceForm.access}
            onChange={(e) => setDatasourceForm({ ...datasourceForm, access: e.target.value })}
            helperText="Proxy: Access via Grafana server. Direct: Access from browser"
          >
            <option value="proxy">Server (Proxy)</option>
            <option value="direct">Browser (Direct)</option>
          </Select>

          {!editingDatasource && ['prometheus', 'loki', 'tempo'].includes(datasourceForm.type) && (
            <div className="">
              <Select
                label="API Key *"
                value={datasourceForm.apiKeyId}
                onChange={(e) => setDatasourceForm({ ...datasourceForm, apiKeyId: e.target.value })}
                required
                helperText="Select which API key to use for multi-tenant data isolation."
              >
                {defaultKey && (
                  <option key={defaultKey.id} value={defaultKey.id}>
                    Default — {defaultKey.name}
                  </option>
                )}
                {(user?.api_keys || []).filter(k => !k.is_default).map((key) => (
                  <option key={key.id} value={key.id}>
                    {key.name}
                  </option>
                ))}
              </Select>
              {(() => {
                let datasourceName;
                if (datasourceForm.type === 'prometheus') {
                  datasourceName = 'Mimir';
                } else if (datasourceForm.type === 'loki') {
                  datasourceName = 'Loki';
                } else {
                  datasourceName = 'Tempo';
                }
                return (
                  <div className="mt-2 text-xs text-sre-text-muted">
                    <span className="material-icons text-sm align-middle mr-1">info</span>
                    This datasource will only query data tagged with this API key in {datasourceName}.
                  </div>
                );
              })()}
            </div>
          )}

          <Checkbox
            label="Set as default datasource"
            checked={datasourceForm.isDefault}
            onChange={(e) => setDatasourceForm({ ...datasourceForm, isDefault: e.target.checked })}
          />

          <div className="border-t border-sre-border pt-4">
            <Select
              label="Visibility"
              value={datasourceForm.visibility}
              onChange={(e) => {
                setDatasourceForm({ ...datasourceForm, visibility: e.target.value, sharedGroupIds: [] })
              }}
              helperText="Control who can access this datasource"
            >
              <option value="private">Private (Only me)</option>
              <option value="group">Shared with Groups</option>
              <option value="tenant">Tenant-wide (Everyone in organization)</option>
            </Select>

            {datasourceForm.visibility === 'group' && (
              <div className="mt-4">
                <label htmlFor="shared-groups" className="block text-sm font-medium text-sre-text mb-2">
                  Shared Groups
                </label>
                <div id="shared-groups" className="space-y-2 max-h-40 overflow-y-auto border border-sre-border rounded p-3">
                  {groups.map(group => (
                    <Checkbox
                      key={group.id}
                      label={group.name}
                      checked={datasourceForm.sharedGroupIds.includes(group.id)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setDatasourceForm({
                            ...datasourceForm,
                            sharedGroupIds: [...datasourceForm.sharedGroupIds, group.id]
                          })
                        } else {
                          setDatasourceForm({
                            ...datasourceForm,
                            sharedGroupIds: datasourceForm.sharedGroupIds.filter(id => id !== group.id)
                          })
                        }
                      }}
                    />
                  ))}
                  {groups.length === 0 && (
                    <p className="text-sm text-sre-text-muted">No groups available</p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </Modal>

      {/* Folder Creator Modal */}
      <Modal
        isOpen={showFolderCreator}
        onClose={() => {
          setShowFolderCreator(false)
          setFolderName('')
        }}
        title="Create New Folder"
        size="sm"
        footer={
          <div className="flex gap-3 justify-end">
            <Button
              variant="ghost"
              onClick={() => {
                setShowFolderCreator(false)
                setFolderName('')
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleCreateFolder}
              disabled={!folderName.trim()}
            >
              Create Folder
            </Button>
          </div>
        }
      >
        <Input
          label="Folder Name *"
          value={folderName}
          onChange={(e) => setFolderName(e.target.value)}
          placeholder="Production Dashboards"
          helperText="Choose a descriptive name for your folder"
          required
          autoFocus
          onKeyDown={(e) => {
            if (e.key === 'Enter' && folderName.trim()) {
              handleCreateFolder()
            }
          }}
        />
      </Modal>

      {/* Confirmation Dialog */}
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
    </div>
  )
}
