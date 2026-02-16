import { Button, Input, Modal, Select } from '../../components/ui'
import HelpTooltip from '../../components/HelpTooltip'
import VisibilitySelector from './VisibilitySelector'
import { VISIBILITY_OPTIONS, GRAFANA_REFRESH_INTERVALS } from '../../utils/constants'

export default function DashboardEditorModal({
  isOpen,
  onClose,
  editingDashboard,
  dashboardForm,
  setDashboardForm,
  editorTab,
  setEditorTab,
  jsonContent,
  setJsonContent,
  jsonError,
  setJsonError,
  fileUploaded,
  setFileUploaded,
  folders,
  datasources,
  groups,
  onSave
}) {
  const handleSave = () => {
    onSave()
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      closeOnOverlayClick={false}
      title={editingDashboard ? 'Edit Dashboard' : 'Create New Dashboard'}
      size="md"
      footer={
        <div className="flex gap-3 justify-end">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={handleSave} disabled={editorTab === 'form' ? !dashboardForm.title.trim() : !jsonContent.trim() || !!jsonError}>
            {editingDashboard ? 'Update Dashboard' : 'Create Dashboard'}
          </Button>
        </div>
      }
    >
      <div>
        <div className="flex gap-2 mb-4 justify-center">
          <button type="button" className={`px-3 py-1 rounded ${editorTab === 'form' ? 'text-sre-text border-b-2 border-sre-primary' : 'bg-transparent text-sre-text-muted'}`} onClick={() => setEditorTab('form')}>Form</button>
          <button type="button" className={`px-3 py-1 rounded ${editorTab === 'json' ? 'text-sre-text border-b-2 border-sre-primary' : 'bg-transparent text-sre-text-muted'}`} onClick={() => setEditorTab('json')}>JSON</button>
        </div>

        {editorTab === 'form' && (
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
              <VisibilitySelector
                visibility={dashboardForm.visibility}
                onVisibilityChange={(value) => setDashboardForm({ ...dashboardForm, visibility: value, sharedGroupIds: [] })}
                sharedGroupIds={dashboardForm.sharedGroupIds}
                onSharedGroupIdsChange={(ids) => setDashboardForm({ ...dashboardForm, sharedGroupIds: ids })}
                groups={groups}
              />
            </div>
          </div>
        )}

        {editorTab === 'json' && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-sre-text mb-3">Upload JSON file</label>
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <input
                    type="file"
                    accept="application/json,.json"
                    onChange={async (e) => {
                      const f = e.target.files && e.target.files[0]
                      if (!f) return
                      try {
                        const txt = await f.text()
                        setJsonContent(txt)
                        setJsonError('')
                        setFileUploaded(true)
                      } catch (err) {
                        setJsonError('Failed to read file')
                        setFileUploaded(false)
                      }
                    }}
                    className="hidden"
                    id="json-file-upload"
                  />
                  <label
                    htmlFor="json-file-upload"
                    className="inline-flex items-center gap-2 px-4 py-2 border border-sre-border rounded-lg bg-sre-surface hover:bg-sre-surface-light text-sre-text cursor-pointer transition-colors"
                  >
                    <span className="material-icons text-sm">upload_file</span>
                    Choose File
                  </label>
                  <span className="text-sm text-sre-text-muted">
                    {fileUploaded ? 'File loaded' : 'No file chosen'}
                  </span>
                </div>
                <p className="text-sm text-sre-text-muted">You can upload a Grafana-exported JSON or paste a dashboard object in the editor below.</p>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">Dashboard JSON</label>
              <textarea className="w-full min-h-[220px] p-3 border rounded bg-sre-bg" value={jsonContent} onChange={(e) => setJsonContent(e.target.value)} placeholder="Paste dashboard JSON here (export from Grafana or raw dashboard object)" />
              {jsonError && <p className="text-sm text-red-500 mt-2">JSON error: {jsonError}</p>}
            </div>
            <div className="border-t border-sre-border pt-4">
              <label className="block text-sm font-medium text-sre-text mb-2">Folder</label>
              <Select value={dashboardForm.folderId} onChange={(e) => setDashboardForm({ ...dashboardForm, folderId: e.target.value })}>
                <option value="0">General</option>
                {folders.map((folder) => (<option key={folder.id} value={folder.id}>{folder.title}</option>))}
              </Select>

              <div className="mt-4">
                <label className="block text-sm font-medium text-sre-text mb-2">Tags (comma-separated)</label>
                <Input value={dashboardForm.tags} onChange={(e) => setDashboardForm({ ...dashboardForm, tags: e.target.value })} placeholder="production, metrics, monitoring" />
              </div>

              <div className="mt-4">
                <label className="block text-sm font-medium text-sre-text mb-2">Visibility</label>
                <VisibilitySelector
                  visibility={dashboardForm.visibility}
                  onVisibilityChange={(value) => setDashboardForm({ ...dashboardForm, visibility: value, sharedGroupIds: [] })}
                  sharedGroupIds={dashboardForm.sharedGroupIds}
                  onSharedGroupIdsChange={(ids) => setDashboardForm({ ...dashboardForm, sharedGroupIds: ids })}
                  groups={groups}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}