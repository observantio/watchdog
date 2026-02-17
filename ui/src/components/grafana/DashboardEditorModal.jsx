`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import React, { useState } from 'react'
import { Button, Input, Modal, Select } from '../../components/ui'
import HelpTooltip from '../../components/HelpTooltip'
import VisibilitySelector from './VisibilitySelector'
import DatasourceSelector from './DatasourceSelector'
import { GRAFANA_REFRESH_INTERVALS } from '../../utils/constants'

const SAMPLE_MIMIR_DASHBOARD = {
  schemaVersion: 38,
  title: 'System & Process Metrics (Mimir)',
  timezone: 'browser',
  refresh: '30s',
  uid: 'system-process-mimir',
  version: 1,
  time: { from: 'now-1h', to: 'now' },
  panels: [
    { type: 'row', title: 'Alerts', gridPos: { x: 0, y: 0, w: 24, h: 1 } },
    { type: 'timeseries', title: 'ALERTS', gridPos: { x: 0, y: 1, w: 12, h: 8 }, datasource: { type: 'prometheus', uid: 'mimir-prometheus' }, targets: [{ expr: 'ALERTS', refId: 'A' }] },
    { type: 'timeseries', title: 'ALERTS_FOR_STATE', gridPos: { x: 12, y: 1, w: 12, h: 8 }, datasource: { type: 'prometheus', uid: 'mimir-prometheus' }, targets: [{ expr: 'ALERTS_FOR_STATE', refId: 'A' }] },

    { type: 'row', title: 'CPU', gridPos: { x: 0, y: 9, w: 24, h: 1 } },
    { type: 'timeseries', title: 'Process CPU Time', gridPos: { x: 0, y: 10, w: 12, h: 8 }, datasource: { uid: 'mimir-prometheus', type: 'prometheus' }, targets: [{ expr: 'rate(process_cpu_time_seconds_total[5m])', refId: 'A' }] },
    { type: 'timeseries', title: 'System CPU Time', gridPos: { x: 12, y: 10, w: 12, h: 8 }, datasource: { uid: 'mimir-prometheus', type: 'prometheus' }, targets: [{ expr: 'rate(system_cpu_time_seconds_total[5m])', refId: 'A' }] },

    { type: 'row', title: 'Memory', gridPos: { x: 0, y: 18, w: 24, h: 1 } },
    { type: 'timeseries', title: 'Process Memory Usage', gridPos: { x: 0, y: 19, w: 12, h: 8 }, datasource: { uid: 'mimir-prometheus', type: 'prometheus' }, targets: [{ expr: 'process_memory_usage_bytes', refId: 'A' }] },
    { type: 'timeseries', title: 'Virtual Memory', gridPos: { x: 12, y: 19, w: 12, h: 8 }, datasource: { uid: 'mimir-prometheus', type: 'prometheus' }, targets: [{ expr: 'process_memory_virtual_bytes', refId: 'A' }] },
    { type: 'timeseries', title: 'System Memory Usage', gridPos: { x: 0, y: 27, w: 12, h: 8 }, datasource: { uid: 'mimir-prometheus', type: 'prometheus' }, targets: [{ expr: 'system_memory_usage_bytes', refId: 'A' }] },

    { type: 'row', title: 'Disk', gridPos: { x: 0, y: 35, w: 24, h: 1 } },
    { type: 'timeseries', title: 'Disk IO Bytes', gridPos: { x: 0, y: 36, w: 12, h: 8 }, datasource: { uid: 'mimir-prometheus', type: 'prometheus' }, targets: [{ expr: 'rate(system_disk_io_bytes_total[5m])', refId: 'A' }] },
    { type: 'timeseries', title: 'Disk Operations', gridPos: { x: 12, y: 36, w: 12, h: 8 }, datasource: { uid: 'mimir-prometheus', type: 'prometheus' }, targets: [{ expr: 'rate(system_disk_operations_total[5m])', refId: 'A' }] },
    { type: 'timeseries', title: 'Disk Pending Ops', gridPos: { x: 0, y: 44, w: 12, h: 8 }, datasource: { uid: 'mimir-prometheus', type: 'prometheus' }, targets: [{ expr: 'system_disk_pending_operations', refId: 'A' }] },
    { type: 'timeseries', title: 'Weighted IO Time', gridPos: { x: 12, y: 44, w: 12, h: 8 }, datasource: { uid: 'mimir-prometheus', type: 'prometheus' }, targets: [{ expr: 'rate(system_disk_weighted_io_time_seconds_total[5m])', refId: 'A' }] },

    { type: 'row', title: 'Network', gridPos: { x: 0, y: 52, w: 24, h: 1 } },
    { type: 'timeseries', title: 'Network IO', gridPos: { x: 0, y: 53, w: 12, h: 8 }, datasource: { uid: 'mimir-prometheus', type: 'prometheus' }, targets: [{ expr: 'rate(system_network_io_bytes_total[5m])', refId: 'A' }] },
    { type: 'timeseries', title: 'Network Errors', gridPos: { x: 12, y: 53, w: 12, h: 8 }, datasource: { uid: 'mimir-prometheus', type: 'prometheus' }, targets: [{ expr: 'rate(system_network_errors_total[5m])', refId: 'A' }] },

    { type: 'row', title: 'Paging & System', gridPos: { x: 0, y: 61, w: 24, h: 1 } },
    { type: 'timeseries', title: 'Paging Faults', gridPos: { x: 0, y: 62, w: 12, h: 8 }, datasource: { uid: 'mimir-prometheus', type: 'prometheus' }, targets: [{ expr: 'rate(system_paging_faults_total[5m])', refId: 'A' }] },
    { type: 'timeseries', title: 'System Uptime', gridPos: { x: 12, y: 62, w: 12, h: 8 }, datasource: { uid: 'mimir-prometheus', type: 'prometheus' }, targets: [{ expr: 'system_uptime_seconds', refId: 'A' }] },
  ],
}

const DASHBOARD_TEMPLATES = [
  {
    id: 'mimir-system-process',
    name: 'System & Process (Mimir)',
    icon: 'monitor_heart',
    summary: 'CPU, memory, disk and network overview for Mimir/Prometheus',
    datasourceUid: 'mimir-prometheus',
    dashboard: SAMPLE_MIMIR_DASHBOARD,
  },
  {
    id: 'empty',
    name: 'Empty Dashboard',
    icon: 'dashboard_customize',
    summary: 'Start from a blank dashboard',
    datasourceUid: '',
    dashboard: { schemaVersion: 38, title: 'Empty Dashboard', uid: 'empty-dashboard', version: 1, time: { from: 'now-1h', to: 'now' }, panels: [] },
  },
]

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
  const [selectedTemplate, setSelectedTemplate] = useState(null)

  const applyTemplate = (template) => {
    setSelectedTemplate(template.id)
    setJsonContent(JSON.stringify(template.dashboard, null, 2))
    setJsonError('')
    setFileUploaded(false)
    if (template.datasourceUid) {
      setDashboardForm({ ...dashboardForm, datasourceUid: template.datasourceUid, useTemplating: true })
    }
  }

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
            <DatasourceSelector
              datasourceUid={dashboardForm.datasourceUid}
              onDatasourceChange={(v) => setDashboardForm({ ...dashboardForm, datasourceUid: v })}
              useTemplating={dashboardForm.useTemplating}
              onUseTemplatingChange={(v) => setDashboardForm({ ...dashboardForm, useTemplating: v })}
              datasources={datasources}
            />
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
            {/* Templates picker */}
            <div className="bg-gradient-to-r from-sre-primary/5 to-sre-primary/10 rounded-xl p-4 border border-sre-primary/20">
              <div className="mb-3 flex items-center gap-3">
                <span className="material-icons text-2xl text-sre-primary">view_quilt</span>
                <div>
                  <h4 className="text-base font-semibold text-sre-text">Templates</h4>
                  <p className="text-sm text-sre-text-muted">Choose a starting dashboard template — click a card to load it into the editor.</p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {DASHBOARD_TEMPLATES.map((t) => {
                  const isSelected = selectedTemplate === t.id
                  const panelTitles = (t.dashboard.panels || []).map(p => p.title).slice(0, 3).join('\n') || 'No panels'
                  return (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => applyTemplate(t)}
                      className={`text-left p-3 rounded-lg border-2 transition-all duration-200 group shadow-sm hover:shadow-md ${
                        isSelected
                          ? 'border-sre-primary bg-sre-primary/10 shadow-md'
                          : 'border-sre-border bg-sre-surface hover:border-sre-primary hover:bg-sre-primary/5'
                      }`}
                      data-testid={t.id === 'mimir-system-process' ? 'load-mimir-sample' : undefined}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className={`text-base font-semibold ${isSelected ? 'text-sre-primary' : 'text-sre-text'}`}>{t.name}</div>
                        <span className="material-icons text-sre-text-muted">{t.icon}</span>
                      </div>
                      <div className="text-sm text-sre-text-muted mb-3 line-clamp-3">{t.summary}</div>
                      <div className="text-xs font-mono text-sre-text-muted bg-sre-bg-alt p-2 rounded border whitespace-pre-wrap leading-relaxed min-h-[48px] overflow-hidden">{panelTitles}</div>
                    </button>
                  )
                })}
              </div>
            </div>

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

                  <span className="text-sm text-sre-text-muted">{fileUploaded ? 'File loaded' : 'No file chosen'}</span>
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
                <DatasourceSelector
                  datasourceUid={dashboardForm.datasourceUid}
                  onDatasourceChange={(v) => setDashboardForm({ ...dashboardForm, datasourceUid: v })}
                  useTemplating={dashboardForm.useTemplating}
                  onUseTemplatingChange={(v) => setDashboardForm({ ...dashboardForm, useTemplating: v })}
                  datasources={datasources}
                />
              </div>

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