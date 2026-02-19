`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getNotificationChannels,
  createNotificationChannel,
  updateNotificationChannel,
  deleteNotificationChannel,
  testNotificationChannel,
  getAllowedChannelTypes,
  listJiraIntegrations,
  createJiraIntegration,
  updateJiraIntegration,
  deleteJiraIntegration,
  getAuthMode,
  getGroups,
} from '../api'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../contexts/ToastContext'
import PageHeader from '../components/ui/PageHeader'
import { Button, Card, Input, Modal, Select, Spinner, Alert } from '../components/ui'
import ConfirmModal from '../components/ConfirmModal'
import ChannelEditor from '../components/alertmanager/ChannelEditor'

const VISIBILITY_TABS = [
  { key: 'private', label: 'Private', icon: 'lock' },
  { key: 'tenant', label: 'Shared By Organization', icon: 'public' },
  { key: 'group', label: 'Shared By Groups', icon: 'groups' },
]

function JiraIntegrationForm({ value, onChange, groups = [], canUseSso = false }) {
  const next = (patch) => onChange({ ...value, ...patch })
  return (
    <div className="space-y-6">
      {/* Basic Information Section */}
      <div className="bg-sre-surface/30 rounded-xl p-6 border border-sre-border/50">
        <h3 className="text-lg font-semibold text-sre-text mb-4 flex items-center gap-2">
          <span className="material-icons text-sre-primary">info</span>
          Basic Information
        </h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="block text-sm font-medium text-sre-text">
              Integration Name
            </label>
            <Input
              value={value.name || ''}
              onChange={(e) => next({ name: e.target.value })}
              placeholder="My Jira Integration"
              className="bg-sre-bg border-sre-border/60 focus:border-sre-primary"
            />
          </div>
          
          <div className="space-y-2">
            <label className="block text-sm font-medium text-sre-text">
              Authentication Mode
            </label>
            <Select
              value={value.authMode || 'api_token'}
              onChange={(e) => next({ authMode: e.target.value })}
              className="bg-sre-bg border-sre-border/60 focus:border-sre-primary"
            >
              <option value="api_token">Email + API token</option>
              <option value="bearer">Bearer token</option>
              {canUseSso && <option value="sso">SSO available (token-based)</option>}
            </Select>
          </div>
        </div>
      </div>

      {/* Configuration Section */}
      <div className="bg-sre-surface/30 rounded-xl p-6 border border-sre-border/50">
        <h3 className="text-lg font-semibold text-sre-text mb-4 flex items-center gap-2">
          <span className="material-icons text-sre-primary">settings</span>
          Configuration
        </h3>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              Jira Base URL <span className="text-red-500">*</span>
            </label>
            <Input
              value={value.baseUrl || ''}
              onChange={(e) => next({ baseUrl: e.target.value })}
              placeholder="https://company.atlassian.net"
              required
              className="bg-sre-bg border-sre-border/60 focus:border-sre-primary"
            />
            <p className="text-xs text-sre-text-muted mt-1">Required. Your Jira instance URL (e.g., https://yourcompany.atlassian.net)</p>
          </div>

          {(value.authMode || 'api_token') === 'api_token' && (
            <>
              <div>
                <label className="block text-sm font-medium text-sre-text mb-2">
                  Jira Account Email
                </label>
                <Input
                  value={value.email || ''}
                  onChange={(e) => next({ email: e.target.value })}
                  className="bg-sre-bg border-sre-border/60 focus:border-sre-primary"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-sre-text mb-2">
                  API Token
                </label>
                <Input
                  type="password"
                  value={value.apiToken || ''}
                  onChange={(e) => next({ apiToken: e.target.value })}
                  className="bg-sre-bg border-sre-border/60 focus:border-sre-primary"
                />
              </div>
            </>
          )}

          {(value.authMode || 'api_token') !== 'api_token' && (
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                {(value.authMode || 'api_token') === 'sso' ? 'SSO Access Token' : 'Bearer Token'}
              </label>
              <Input
                type="password"
                value={value.bearerToken || ''}
                onChange={(e) => next({ bearerToken: e.target.value })}
                className="bg-sre-bg border-sre-border/60 focus:border-sre-primary"
              />
            </div>
          )}
        </div>
      </div>

      {/* Settings Section */}
      <div className="bg-sre-surface/30 rounded-xl p-6 border border-sre-border/50">
        <h3 className="text-lg font-semibold text-sre-text mb-4 flex items-center gap-2">
          <span className="material-icons text-sre-primary">tune</span>
          Settings
        </h3>
        
        <div className="space-y-4">
          <label className="flex items-center gap-3 p-3 bg-sre-bg/50 rounded-lg border border-sre-border/30 hover:border-sre-primary/30 transition-colors cursor-pointer">
            <input
              type="checkbox"
              checked={!!value.enabled}
              onChange={(e) => next({ enabled: e.target.checked })}
              className="w-5 h-5 text-sre-primary border-sre-border rounded focus:ring-sre-primary focus:ring-2"
            />
            <div className="flex-1">
              <div className="font-medium text-sre-text">Enable this integration</div>
              <div className="text-sm text-sre-text-muted">Only enabled integrations will be available for use</div>
            </div>
          </label>
        </div>
      </div>
    </div>
  )
}

export default function IntegrationsPage() {
  const { user } = useAuth()
  const { toast } = useToast()

  const formatApiError = (err) => {
    if (!err) return 'API error'

    // Prefer explicit error body from our API client (err.body), otherwise
    // fall back to the error object/string/message.
    let body = err && err.body ? err.body : err

    if (typeof body === 'string') {
      try {
        body = JSON.parse(body)
      } catch (_) {
        // leave as string and fall through to message handling below
      }
    }

    if (body) {
      if (typeof body === 'string') return body
      if (typeof body.errors === 'string') return body.errors
      if (Array.isArray(body.errors)) return body.errors.join('; ')
      if (body.errors && typeof body.errors === 'object') {
        const flat = []
        Object.values(body.errors).forEach(v => {
          if (Array.isArray(v)) flat.push(...v)
          else if (v) flat.push(String(v))
        })
        if (flat.length) return flat.join('; ')
      }
      if (typeof body.detail === 'string') return body.detail
      if (typeof body.message === 'string') return body.message
      try { return JSON.stringify(body) } catch (_) { /* fallthrough */ }
    }

    const m = err && err.message
    if (m && typeof m === 'string') {
      // message may itself be a JSON-encoded string
      try {
        const parsed = JSON.parse(m)
        if (parsed) {
          if (Array.isArray(parsed.errors)) return parsed.errors.join('; ')
          if (parsed.detail) return parsed.detail
          if (parsed.message) return parsed.message
          return String(parsed)
        }
      } catch (_) {}
      return m
    }

    return String(err)
  }

  const [activeTab, setActiveTab] = useState('private')
  const [channels, setChannels] = useState([])
  const [allowedChannelTypes, setAllowedChannelTypes] = useState([])
  const [groups, setGroups] = useState([])
  const [jiraIntegrations, setJiraIntegrations] = useState([])
  const [canUseSso, setCanUseSso] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [showChannelModal, setShowChannelModal] = useState(false)
  const [editingChannel, setEditingChannel] = useState(null)
  const [showJiraModal, setShowJiraModal] = useState(false)
  const [editingJira, setEditingJira] = useState(null)
  const [showTestModal, setShowTestModal] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState({ show: false, type: '', id: '', name: '' })
  const [jiraForm, setJiraForm] = useState({
    name: '',
    visibility: 'private',
    sharedGroupIds: [],
    enabled: true,
    baseUrl: '',
    email: '',
    apiToken: '',
    bearerToken: '',
    authMode: 'api_token',
  })

  const userId = user?.id

  useEffect(() => {
    loadAll()
  }, [])

  async function loadAll() {
    setLoading(true)
    setError(null)
    try {
      const [channelsData, allowedTypesData, groupsData, jiraData, authModeData] = await Promise.all([
        getNotificationChannels().catch(() => []),
        getAllowedChannelTypes().catch(() => ({ allowedTypes: [] })),
        getGroups().catch(() => []),
        listJiraIntegrations().catch(() => ({ items: [] })),
        getAuthMode().catch(() => ({ oidc_enabled: false })),
      ])
      setChannels(
        Array.isArray(channelsData)
          ? channelsData.map((channel) => ({
              ...channel,
              sharedGroupIds: channel?.sharedGroupIds || channel?.shared_group_ids || [],
            }))
          : []
      )
      setAllowedChannelTypes(Array.isArray(allowedTypesData?.allowedTypes) ? allowedTypesData.allowedTypes : [])
      setGroups(Array.isArray(groupsData) ? groupsData : [])
      setJiraIntegrations(
        Array.isArray(jiraData?.items)
          ? jiraData.items.map((integration) => ({
              ...integration,
              sharedGroupIds: integration?.sharedGroupIds || integration?.shared_group_ids || [],
            }))
          : []
      )
      setCanUseSso(!!authModeData?.oidc_enabled)
    } catch (e) {
      setError(e?.message || 'Failed to load integrations')
    } finally {
      setLoading(false)
    }
  }

  const visibleChannels = useMemo(() => channels.filter((channel) => channel.visibility === activeTab), [channels, activeTab])
  const visibleJiraIntegrations = useMemo(() => jiraIntegrations.filter((item) => item.visibility === activeTab), [jiraIntegrations, activeTab])

  const channelIconForType = (type) => {
    const t = (type || '').toLowerCase()
    if (t.includes('slack')) return 'chat'
    if (t.includes('email')) return 'email'
    if (t.includes('webhook') || t.includes('web')) return 'link'
    if (t.includes('sms') || t.includes('pager')) return 'notifications'
    return 'notifications'
  }

  const channelColorForType = (type) => {
    const t = (type || '').toLowerCase()
    if (t.includes('slack')) return 'from-emerald-100 to-emerald-50 text-emerald-700 dark:from-emerald-900/20 dark:text-emerald-300'
    if (t.includes('email')) return 'from-yellow-100 to-yellow-50 text-amber-700 dark:from-yellow-900/20 dark:text-amber-300'
    if (t.includes('webhook') || t.includes('web')) return 'from-sky-100 to-sky-50 text-sky-700 dark:from-sky-900/20 dark:text-sky-300'
    if (t.includes('sms') || t.includes('pager')) return 'from-orange-100 to-orange-50 text-orange-700 dark:from-orange-900/20 dark:text-orange-300'
    return 'from-gray-100 to-gray-50 text-gray-700 dark:from-gray-900/20 dark:text-gray-300'
  }

  const navigate = useNavigate()

  const openCreateChannel = () => {
    setEditingChannel(null)
    setShowChannelModal(true)
  }

  const openEditChannel = (channel) => {
    setEditingChannel(channel)
    setShowChannelModal(true)
  }

  const openCreateJira = () => {
    setEditingJira(null)
    setJiraForm({
      name: '',
      visibility: activeTab,
      sharedGroupIds: [],
      enabled: true,
      baseUrl: '',
      email: '',
      apiToken: '',
      bearerToken: '',
      authMode: canUseSso ? 'sso' : 'api_token',
    })
    setShowJiraModal(true)
  }

  const openEditJira = (integration) => {
    setEditingJira(integration)
    setJiraForm({
      name: integration.name || '',
      visibility: integration.visibility || 'private',
      sharedGroupIds: integration.sharedGroupIds || integration.shared_group_ids || [],
      enabled: !!integration.enabled,
      baseUrl: integration.baseUrl || '',
      email: integration.email || '',
      apiToken: '',
      bearerToken: '',
      authMode: integration.authMode || 'api_token',
    })
    setShowJiraModal(true)
  }

  /* Local presentational components to reduce duplication and improve readability */
  function ChannelCard({ channel }) {
    const isOwner = channel.createdBy === userId
    const typeIcon = channelIconForType(channel.type)
    const colorClasses = channelColorForType(channel.type)

    return (
      <div className="group relative p-4 rounded-xl border border-sre-border bg-gradient-to-br from-white/3 to-white/6 shadow-sm hover:shadow-lg transition-all transform hover:-translate-y-0.5">
        <div className="flex items-start gap-4">
          <div className={`w-12 h-12 rounded-lg flex items-center justify-center bg-gradient-to-br ${colorClasses} font-semibold`}>
            <span className="material-icons text-lg leading-none">{typeIcon}</span>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <div className="font-semibold text-sre-text truncate">{channel.name}</div>
                  <div className="text-xs text-sre-text-muted rounded px-2 py-1 bg-sre-surface/40 border border-sre-border/30">{channel.visibility || 'private'}</div>
                </div>
                <div className="text-xs text-sre-text-muted mt-2 truncate">{channel.description || '—'}</div>
              </div>

              <div className="flex flex-col items-end gap-2">
                <div className={`inline-flex items-center gap-2 px-2 py-1 rounded-full text-xs font-medium ${channel.enabled ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'}`}>
                  <span className={`w-2 h-2 rounded-full ${channel.enabled ? 'bg-green-600' : 'bg-gray-400'}`} />
                  {channel.enabled ? 'Enabled' : 'Disabled'}
                </div>

                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  {isOwner && (
                    <Button size="sm" variant="ghost" aria-label="Test channel" title="Test channel" onClick={() => handleTestChannel(channel.id)} className="p-1 hover:bg-sre-primary/10">
                      <span className="material-icons text-base">play_arrow</span>
                    </Button>
                  )}
                  {isOwner && (
                    <Button size="sm" variant="ghost" aria-label="Edit channel" title="Edit channel" onClick={() => openEditChannel(channel)} className="p-1 hover:bg-sre-primary/10">
                      <span className="material-icons text-base">edit</span>
                    </Button>
                  )}
                  {isOwner && (
                    <Button size="sm" variant="ghost" aria-label="Delete channel" title="Delete channel" onClick={() => setDeleteConfirm({ show: true, type: 'channel', id: channel.id, name: channel.name })} className="p-1 hover:bg-sre-primary/10">
                      <span className="material-icons text-base">delete</span>
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  function JiraCard({ integration }) {
    const isOwner = integration.createdBy === userId
    return (
      <div className="p-4 rounded-xl border border-sre-border bg-white/3 shadow-sm hover:shadow-md transition-all hover:border-sre-primary/30">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-lg flex items-center justify-center bg-gradient-to-br from-indigo-100 to-indigo-50 text-indigo-700 font-semibold dark:from-indigo-900/30 dark:to-indigo-800/30 dark:text-indigo-400">
            <span className="material-icons">account_tree</span>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-3 mb-2">
              <div className="font-semibold text-sre-text truncate">{integration.name}</div>
              <div className="text-xs text-sre-text-muted">{integration.visibility || 'private'}</div>
            </div>
            <div className="text-sm text-sre-text-muted truncate mb-3">{integration.baseUrl}</div>

            <div className="flex items-center gap-2 justify-end">
              {isOwner && (
                <Button size="sm" variant="ghost" aria-label="Edit integration" title="Edit integration" onClick={() => openEditJira(integration)} className="p-1 hover:bg-sre-primary/10">
                  <span className="material-icons text-base">edit</span>
                </Button>
              )}
              {isOwner && (
                <Button size="sm" variant="ghost" aria-label="Delete integration" title="Delete integration" onClick={() => setDeleteConfirm({ show: true, type: 'Jira integration', id: integration.id, name: integration.name })} className="p-1 hover:bg-sre-primary/10">
                  <span className="material-icons text-base">delete</span>
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    )
  }

  async function handleSaveChannel(payload) {
    try {
      const visibilityToUse = payload?.visibility || editingChannel?.visibility || activeTab
      const finalPayload = {
        ...payload,
        visibility: visibilityToUse,
        sharedGroupIds: visibilityToUse === 'group' ? (payload.sharedGroupIds || []) : [],
      }
      if (editingChannel?.id) {
        await updateNotificationChannel(editingChannel.id, finalPayload)
      } else {
        await createNotificationChannel(finalPayload)
      }
      setShowChannelModal(false)
      await loadAll()
      toast.success('Channel saved')
    } catch (e) {
      toast.error(formatApiError(e) || 'Failed to save channel')
    }
  }

  async function handleDeleteChannel(channelId) {
    try {
      await deleteNotificationChannel(channelId)
      await loadAll()
      toast.success('Channel deleted')
    } catch (e) {
      toast.error(formatApiError(e) || 'Failed to delete channel')
    }
  }

  async function handleTestChannel(channelId) {
    try {
      const result = await testNotificationChannel(channelId)
      setTestResult(result)
      setShowTestModal(true)
    } catch (e) {
      toast.error(formatApiError(e) || 'Failed to test channel')
    }
  }

  async function handleSaveJiraIntegration() {
    // Validate required fields
    if (!jiraForm.baseUrl || !jiraForm.baseUrl.trim()) {
      toast.error('Jira Base URL is required')
      return
    }

    // Basic URL validation
    try {
      new URL(jiraForm.baseUrl.trim())
    } catch (e) {
      toast.error('Jira Base URL must be a valid URL (https://company.atlassian.net)')
      return
    }

    if (!jiraForm.name || !jiraForm.name.trim()) {
      toast.error('Integration name is required')
      return
    }

    try {
      const visibilityToUse = editingJira?.visibility || activeTab
      const payload = {
        ...jiraForm,
        baseUrl: jiraForm.baseUrl.trim(),
        name: jiraForm.name.trim(),
        visibility: visibilityToUse,
        sharedGroupIds: visibilityToUse === 'group' ? (jiraForm.sharedGroupIds || []) : [],
      }
      if (editingJira?.id) {
        await updateJiraIntegration(editingJira.id, payload)
      } else {
        await createJiraIntegration(payload)
      }
      setShowJiraModal(false)
      await loadAll()
      toast.success('Jira integration saved')
    } catch (e) {
      toast.error(formatApiError(e) || 'Failed to save Jira integration')
    }
  }

  async function handleDeleteJiraIntegration(integrationId) {
    try {
      await deleteJiraIntegration(integrationId)
      await loadAll()
      toast.success('Jira integration deleted')
    } catch (e) {
      toast.error(formatApiError(e) || 'Failed to delete Jira integration')
    }
  }

  if (loading) {
    return <div className="py-12"><Spinner size="lg" /></div>
  }

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        icon="integration_instructions"
        title="Integrations"
        subtitle="Manage notification channels and Jira integrations with private, group, and organization scopes."
      />

      {error && <Alert variant="error">{error}</Alert>}

      <div className="flex gap-2 border-b border-sre-border justify-center items-center">
        {VISIBILITY_TABS.map((tab) => (
          <button
            type="button"
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`pl-4 pr-4 py-2 text-sm flex items-center justify-center gap-2 border-b-2 transition-colors ${
              activeTab === tab.key
                ? 'border-sre-primary text-sre-primary'
                : 'border-transparent text-sre-text-muted hover:text-sre-text'
            }`}
          >
            <span className="material-icons text-sm">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      <div className="space-y-6">
        {/* Notification Channels */}
        <Card className="py-6 px-0">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div>
              <h2 className="text-xl font-semibold text-sre-text">Notification Channels</h2>
              <p className="text-sm text-sre-text-muted mt-1">Create and manage channels to receive alerts via Email, Slack, Webhooks and more.</p>
            </div>
            <div className="flex items-center gap-3">
              <Button
                onClick={openCreateChannel}
                aria-label="Add channel"
                size="sm"
                variant="primary"
                className="h-9 w-9 p-0 text-white border border-sre-primary/40 shadow-md hover:shadow-lg"
              >
                <span className="material-icons text-lg leading-none">add</span>
              </Button>
            </div>
          </div>

          <div className="space-y-4">
            {visibleChannels.length === 0 ? (
              <div className="text-center py-12">
                <div className="mx-auto w-36 h-36 rounded-full bg-gradient-to-br from-sre-surface/50 to-sre-surface/30 flex items-center justify-center mb-4 shadow-inner">
                  <span className="material-icons text-5xl text-sre-text-muted">notifications_off</span>
                </div>
                <h3 className="text-lg font-semibold text-sre-text mb-2">No channels in this scope</h3>
                <p className="text-sm text-sre-text-muted max-w-[34rem] mx-auto mb-6">No notification channels are configured for this scope yet. Create a channel to start sending alerts to Slack, Email, Webhooks or other destinations.</p>
                <div className="flex items-center justify-center gap-3">
                  <Button onClick={openCreateChannel} variant="primary" className="px-4 py-2">
                    <span className="material-icons mr-2">add</span>Create channel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {visibleChannels.map((channel) => <ChannelCard key={channel.id} channel={channel} />)}
              </div>
            )}
          </div>
        </Card>

        <hr className="border-sre-border" />

        {/* Jira Integrations */}
        <Card className="py-6 px-0">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div>
              <h2 className="text-xl font-semibold text-sre-text">Jira Integrations</h2>
              <p className="text-sm text-sre-text-muted mt-1">Connect Jira to create and sync issues and comments from incidents.</p>
            </div>
            <div className="flex items-center gap-3">
              <Button
                onClick={openCreateJira}
                aria-label="Add Jira integration"
                size="sm"
                variant="primary"
                className="h-9 w-9 p-0 text-white border border-sre-primary/40 shadow-md hover:shadow-lg"
              >
                <span className="material-icons text-lg leading-none">add</span>
              </Button>
            </div>
          </div>

          <div className="space-y-4">
            {visibleJiraIntegrations.length === 0 ? (
              <div className="text-center py-12">
                <div className="mx-auto w-32 h-32 bg-sre-surface/60 flex items-center justify-center mb-4">
                  <span className="material-icons text-4xl text-sre-text-muted">integration_instructions</span>
                </div>
                <h3 className="text-lg font-semibold text-sre-text mb-2">No Jira integrations in this scope</h3>
                <p className="text-sm text-sre-text-muted max-w-[28rem] mx-auto mb-4">Add a Jira integration to enable creating issues directly from incidents and syncing comments.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {visibleJiraIntegrations.map((integration) => <JiraCard key={integration.id} integration={integration} />)}
              </div>
            )}
          </div>
        </Card>
      </div>

      <Modal
        isOpen={showChannelModal}
        onClose={() => setShowChannelModal(false)}
        title={editingChannel ? 'Edit Channel' : 'Create Channel'}
        size="lg"
        closeOnOverlayClick={false}
      >
        <ChannelEditor
          channel={editingChannel}
          onSave={handleSaveChannel}
          onCancel={() => setShowChannelModal(false)}
          allowedTypes={allowedChannelTypes}
          visibility={activeTab}
        />
      </Modal>

      <Modal
        isOpen={showJiraModal}
        onClose={() => setShowJiraModal(false)}
        title={editingJira ? 'Edit Jira Integration' : 'Create Jira Integration'}
        size="lg"
        closeOnOverlayClick={false}
      >
        <JiraIntegrationForm
          value={jiraForm}
          onChange={setJiraForm}
          groups={groups}
          canUseSso={canUseSso}
        />

        {/* Action Buttons */}
        <div className="flex justify-end gap-3 pt-4 border-t border-sre-border/50 mt-6">
          <Button 
            type="button" 
            variant="ghost" 
            onClick={() => setShowJiraModal(false)}
            className="px-6 py-2"
          >
            Cancel
          </Button>
          <Button 
            onClick={handleSaveJiraIntegration}
            className="px-6 py-2 bg-sre-primary hover:bg-sre-primary-light text-white shadow-lg hover:shadow-xl transition-all"
          >
            <span className="material-icons text-sm mr-2">save</span>
            Save Integration
          </Button>
        </div>
      </Modal>

      <Modal
        isOpen={showTestModal}
        onClose={() => setShowTestModal(false)}
        title="Test Notification Result"
        size="lg"
      >
        <div className="space-y-4">
          <div className="bg-sre-surface p-4 rounded text-lg text-sre-text text-center">
            {testResult?.message || 'No message'}
          </div>
          <div className="flex justify-end">
            <Button onClick={() => setShowTestModal(false)}>Close</Button>
          </div>
        </div>
      </Modal>

      <ConfirmModal
        isOpen={deleteConfirm.show}
        onCancel={() => setDeleteConfirm({ show: false, type: '', id: '', name: '' })}
        onConfirm={async () => {
          // snapshot the target (avoid reading `deleteConfirm` after async waits)
          const target = { ...deleteConfirm }
          // close modal immediately to prevent race/propagation re-open issues
          setDeleteConfirm({ show: false, type: '', id: '', name: '' })
          try {
            if (target.type === 'channel') {
              await handleDeleteChannel(target.id)
            } else if (target.type === 'Jira integration') {
              await handleDeleteJiraIntegration(target.id)
            }
          } catch (e) {
            // Error already handled in handleDelete functions — re-open so user can retry
            setDeleteConfirm(target)
          }
        }}
        title="Confirm Delete"
        message={`Are you sure you want to delete the ${deleteConfirm.type} "${deleteConfirm.name}"? This action cannot be undone.`}
        confirmText="Delete"
        cancelText="Cancel"
        variant="danger"
      />
    </div>
  )
}
