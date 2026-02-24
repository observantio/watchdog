`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { useState, useEffect, useMemo } from 'react'
import PageHeader from '../components/ui/PageHeader'
import { Card, Input, Button, Select, Modal, Checkbox } from '../components/ui'
import ConfirmModal from '../components/ConfirmModal'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../contexts/ToastContext' 
import HelpTooltip from '../components/HelpTooltip'
import * as api from '../api'
import { OTLP_GATEWAY_HOST } from '../utils/constants'
import { buildOtelYaml } from '../utils/otelConfig'

export default function ApiKeyPage() {
  const { user, updateUser } = useAuth()
  const toast = useToast()
  const [orgId, setOrgId] = useState('')
  const [apiKeys, setApiKeys] = useState([])

  const [newKeyName, setNewKeyName] = useState('')
  const [newKeyValue, setNewKeyValue] = useState('')
  const [loading, setLoading] = useState(false)

  const [showKeyId, setShowKeyId] = useState(null)
  const [showDefaultModal, setShowDefaultModal] = useState(false)
  const [showAddModal, setShowAddModal] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [keyToDelete, setKeyToDelete] = useState(null)
  const [showShareModal, setShowShareModal] = useState(false)
  const [keyToShare, setKeyToShare] = useState(null)
  const [allUsers, setAllUsers] = useState([])
  const [allGroups, setAllGroups] = useState([])
  const [shareSearch, setShareSearch] = useState('')
  const [selectedShareUserIds, setSelectedShareUserIds] = useState([])
  const [selectedShareGroupIds, setSelectedShareGroupIds] = useState([])

  useEffect(() => {
    if (user) {
      setApiKeys(user.api_keys || [])
      const defaultKey = (user.api_keys || []).find((k) => k.is_default)
      const orgKey = defaultKey
        || (user.api_keys || []).find((k) => k.key === user.org_id)
      setOrgId(orgKey?.id || '')
    }
  }, [user])

  const refreshUser = async () => {
    const updatedUser = await api.getCurrentUser()
    updateUser(updatedUser)
    setApiKeys(updatedUser.api_keys || [])
  }

  const loadUsers = async () => {
    try {
      const users = await api.getUsers()
      setAllUsers(Array.isArray(users) ? users : [])
    } catch {
      setAllUsers([])
    }
  }

  const loadGroups = async () => {
    try {
      const groups = await api.getGroups()
      setAllGroups(Array.isArray(groups) ? groups : [])
    } catch {
      setAllGroups([])
    }
  }

  const handleSaveOrgId = async (e) => {
    if (e && typeof e.preventDefault === 'function') e.preventDefault()
    setLoading(true)
    try {
      if (!orgId) {
        toast.error('Please select an API key')
        setLoading(false)
        return
      }
      await api.updateApiKey(orgId, { is_default: true })
      await refreshUser()
      toast.success('Default API key updated successfully.')
      setShowDefaultModal(false)
    } catch (err) {
      const msg = err.body?.detail || err.message || 'Failed to update default API key'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleCreateKey = async (e) => {
    if (e && typeof e.preventDefault === 'function') e.preventDefault()
    if (!newKeyName.trim()) {
      toast.error('Key name is required')
      return
    }
    setLoading(true)
    try {
      await api.createApiKey({ name: newKeyName.trim(), key: newKeyValue.trim() || undefined })
      setNewKeyName('')
      setNewKeyValue('')
      await refreshUser()
      toast.success('API key created successfully.')
      setShowAddModal(false)
    } catch (err) {
      const msg = err.body?.detail || err.message || 'Failed to create API key'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleActivateKey = async (key) => {
    try {
      await api.updateApiKey(key.id, { is_enabled: true })
      await refreshUser()
      toast.success('API key activated')
    } catch (err) {
      const msg = err.body?.detail || err.message || 'Failed to update API key'
      toast.error(msg)
    }
  }

  const handleDeleteKey = async (key) => {
    try {
      await api.deleteApiKey(key.id)
      await refreshUser()
      toast.success('API key deleted successfully.')
    } catch (err) {
      if (err?.status === 403) {
        toast.error('You are not authorized to delete this key')
        return
      }
      const msg = err.body?.detail || err.message || 'Failed to delete API key'
      toast.error(msg)
    }
  }

  const openShareModal = async (key) => {
    setKeyToShare(key)
    setSelectedShareUserIds((key?.shared_with || []).map((item) => item.user_id))
    setSelectedShareGroupIds([])
    setShareSearch('')
    setShowShareModal(true)
    if (!allUsers.length) {
      await loadUsers()
    }
    if (!allGroups.length) {
      await loadGroups()
    }
  }

  const handleSaveShares = async () => {
    if (!keyToShare) return
    setLoading(true)
    try {
      await api.replaceApiKeyShares(keyToShare.id, selectedShareUserIds, selectedShareGroupIds)
      await refreshUser()
      toast.success('API key sharing updated')
      setShowShareModal(false)
      setKeyToShare(null)
      setSelectedShareUserIds([])
      setSelectedShareGroupIds([])
    } catch (err) {
      toast.error(err.body?.detail || err.message || 'Failed to update API key sharing')
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = async (value, successMessage) => {
    try {
      await navigator.clipboard.writeText(value)
      toast.success(successMessage)
    } catch (err) {
      const msg = 'Failed to copy to clipboard'
      toast.error(msg)
    }
  }

  const handleDownloadYaml = (content) => {
    try {
      const blob = new Blob([content], { type: 'text/yaml' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'otel-agent.yaml'
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
      toast.success('YAML downloaded')
    } catch (err) {
      const msg = 'Failed to download YAML'
      toast.error(msg)
    }
  }

  const selectedOrgKeyValue = useMemo(() => {
    const found = apiKeys.find((k) => k.id === orgId)
    return found?.key || user?.org_id || ''
  }, [apiKeys, orgId, user])

  // YAML modal state
  const [showYamlModal, setShowYamlModal] = useState(false)
  const [yamlModalKeyId, setYamlModalKeyId] = useState('')
  const [gatewayHost, setGatewayHost] = useState(OTLP_GATEWAY_HOST)

  const [yamlShowToken, setYamlShowToken] = useState(false)

  const yamlModalToken = useMemo(() => {
    const found = apiKeys.find((k) => k.id === yamlModalKeyId)
    return found?.otlp_token || ''
  }, [apiKeys, yamlModalKeyId])

  useEffect(() => {
    setYamlShowToken(false)
  }, [yamlModalKeyId, showYamlModal])

  // derive endpoints from the gateway host
  const derivedLoki = useMemo(() => `${gatewayHost.replace(/\/$/, '')}/loki/otlp`, [gatewayHost])
  const derivedTempo = useMemo(() => `${gatewayHost.replace(/\/$/, '')}/tempo`, [gatewayHost])
  const derivedMimir = useMemo(() => `${gatewayHost.replace(/\/$/, '')}/mimir/api/v1/push`, [gatewayHost])

  const yamlModalContent = useMemo(() => buildOtelYaml(yamlModalToken || '', {
    lokiEndpoint: derivedLoki,
    tempoEndpoint: derivedTempo,
    mimirEndpoint: derivedMimir
  }), [yamlModalToken, derivedLoki, derivedTempo, derivedMimir])

  const enabledCount = apiKeys.filter((k) => k.is_enabled).length
  const activeKeyCandidate = apiKeys.find((k) => k.is_enabled) || apiKeys.find((k) => k.is_default) || apiKeys[0] || null
  const isYamlKeyShared = Boolean(apiKeys.find((k) => k.id === yamlModalKeyId)?.is_shared)

  const filteredShareUsers = useMemo(() => {
    const q = shareSearch.trim().toLowerCase()
    if (!q) return allUsers
    return allUsers.filter((u) => [u.username, u.email, u.full_name, u.id].some((v) => `${v || ''}`.toLowerCase().includes(q)))
  }, [allUsers, shareSearch])

  const myShareableGroups = useMemo(() => {
    const myGroupIds = new Set((Array.isArray(user?.group_ids) ? user.group_ids : []).map((id) => String(id)))
    return allGroups.filter((group) => myGroupIds.has(String(group?.id || '')))
  }, [allGroups, user])

  function formatDisplayKey(key) {
    if (showKeyId === key.id) return key.key || '-'
    if (key.key) return `${key.key.slice(0, 6)}...${key.key.slice(-4)}`
    return '-'
  }

  return (
    <div className="animate-fade-in max-w-7xl mx-auto">
      <PageHeader
        icon="key"
        title="API Keys"
        subtitle="Manage tenant keys for logs, traces and metrics. Use keys to isolate datasets per product or team."
      />



      <div className="space-y-8">
        <div>
          <Card className="p-3 rounded-lg border border-sre-border shadow-sm bg-sre-surface">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-sre-text">Key Actions</h3>
                <p className="text-xs text-sre-text-muted mt-1">Update the default API key, add a new key, or generate an OTEL agent config.</p>
              </div>
              <div className="flex items-center gap-3">
                <Button size="sm" variant="secondary" className="py-1 px-3" onClick={() => setShowDefaultModal(true)}>Update Default Key</Button>
                <Button size="sm" className="py-1 px-3" onClick={() => setShowAddModal(true)}>Add New Key</Button>
                <Button
                  size="sm"
                  variant="secondary"
                  className="py-1 px-3"
                  onClick={() => {
                    if (!activeKeyCandidate || activeKeyCandidate.is_shared) return
                    setYamlModalKeyId(activeKeyCandidate.id)
                    setShowYamlModal(true)
                  }}
                  disabled={!!activeKeyCandidate?.is_shared}
                  aria-disabled={!!activeKeyCandidate?.is_shared}
                >
                  Generate Agent YAML
                </Button>
              </div>
            </div>
          </Card>
        </div>

        <Card title={`API Keys (${apiKeys.length})`} subtitle={`Enabled: ${enabledCount}`} className="p-4 rounded-lg border border-sre-border shadow-sm bg-sre-surface">
          <p className="text-xs text-sre-text-muted mt-2">These API keys are local to your tenant and may be shared with other teams in your organization, since they scope to your tenant. <strong>However, never share the OTLP token included in the generated OTEL Agent YAML — keep it secret.</strong></p>
          {apiKeys.length === 0 ? (
            <div className="p-4 text-sm text-sre-text-muted">No API keys found.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="bg-sre-surface text-sre-text-muted text-xs uppercase tracking-wide">
                    <th className="py-3 pl-0 pr-4">Name</th>
                    <th className="py-3 px-4">Key</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Actions</th>
                  </tr>
                </thead>
                <tbody >
                  {apiKeys.map((key) => (
                    <tr key={key.id} className="align-top hover:bg-sre-background">
                      <td className="py-3 pl-0 pr-4">
                        <div className="font-medium text-sre-text">{key.name}</div>
                        {key.is_default && <div className="text-xs text-sre-text-muted">Default</div>}
                        {key.is_shared && key.owner_username && <div className="text-xs text-sre-text-muted">Shared by {key.owner_username}</div>}
                      </td>
                      <td className="py-3 px-4 text-xs text-sre-text-muted break-all">
                        <div className="flex items-center gap-3">
                          <div className="font-mono text-xs">
                            {formatDisplayKey(key)}
                          </div>
                          <div className="flex items-center gap-2">
                            <Button size="sm" variant="ghost" onClick={() => setShowKeyId(showKeyId === key.id ? null : key.id)}>
                              {showKeyId === key.id ? 'Hide' : 'Show'}
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => handleCopy(key.key, 'API key copied to clipboard')}>
                              Copy
                            </Button>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <input
                            type="radio"
                            name="active-api-key"
                            className="h-4 w-4"
                            checked={key.is_enabled}
                            onChange={() => handleActivateKey(key)}
                          />
                          <div className="text-sm">
                            {key.is_enabled ? <span className="text-green-600">Active</span> : <span className="text-sre-text-muted">Inactive</span>}
                          </div>
                        </div>
                      </td>
                      <td className="py-2 px-4">
                        <div className="flex gap-2">
                          {!key.is_shared && (
                            <Button size="sm" variant="primary" onClick={() => openShareModal(key)} aria-label={`Share ${key.name}`}>Share</Button>
                          )}
                          {!key.is_default && (
                            <Button size="sm" variant="danger" onClick={() => { setKeyToDelete(key); setShowDeleteConfirm(true); }} aria-label={`Delete ${key.name}`}>Delete</Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>



        <ConfirmModal
          isOpen={showDeleteConfirm}
          title="Delete API Key"
          message={keyToDelete ? `Are you sure you want to delete the API key "${keyToDelete.name}"? This action cannot be undone. While you can create the same Org ID, you cannot create the same OTLP token, so ensure you know before expiring those OTEL agents.` : 'Are you sure you want to delete this API key? This action cannot be undone. While you can create the same Org ID, you cannot create the same OTLP token, so ensure you know before expiring those OTEL agents.'}
          onConfirm={async () => {
            if (keyToDelete) await handleDeleteKey(keyToDelete)
            setShowDeleteConfirm(false)
            setKeyToDelete(null)
          }}
          onCancel={() => { setShowDeleteConfirm(false); setKeyToDelete(null) }}
          confirmText="Delete"
          cancelText="Cancel"
          variant="danger"
        />

        {/* Default key modal */}
        <Modal isOpen={showDefaultModal} onClose={() => setShowDefaultModal(false)} title="Update Default API Key"  size="md" closeOnOverlayClick={false}>
          <form onSubmit={handleSaveOrgId} className="space-y-4" onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSaveOrgId(e)
            }
          }}>
            <Select value={orgId} onChange={(e) => setOrgId(e.target.value)} className="w-full" required>
              {apiKeys.length === 0 ? (
                <option value="">No API keys available</option>
              ) : (
                apiKeys.map((k) => (
                  <option key={k.id} value={k.id}>{k.name} {k.is_default ? '(Default)' : ''}</option>
                ))
              )}
            </Select>

            <div className="text-xs text-sre-text-muted">
              <strong>Note:</strong> This assigns the <em>default</em> API key — it is not the active key used for immediate viewing. Select the active key to change which product's data you are viewing; the default key is what will be recommended when creating Grafana datasources and similar integrations.
            </div>

            <div className="flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setShowDefaultModal(false)}>Cancel</Button>
              <Button type="submit" loading={loading}>Save</Button>
            </div>
          </form>
        </Modal>
        <Modal isOpen={showAddModal} onClose={() => setShowAddModal(false)} title="Add API Key" size="md" closeOnOverlayClick={false}>
          <form onSubmit={handleCreateKey} className="space-y-4" onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleCreateKey(e)
            }
          }}>
            <div>
              <div className="flex items-center justify-between">
                <label className="block text-sm font-medium text-sre-text mb-2">Key Name</label>
                <HelpTooltip text="A descriptive name for this API key, e.g., the name of the application or service using it." />
              </div>
              <Input value={newKeyName} onChange={(e) => setNewKeyName(e.target.value)} placeholder="XYZ Product" required />
            </div>
            <div>
              <div className="flex items-center justify-between">
                <label className="block text-sm font-medium text-sre-text mb-2">Key Value (optional)</label>
                <HelpTooltip text="The secret value for the API key. If left empty, a secure random value will be generated." />
              </div>
              <Input value={newKeyValue} onChange={(e) => setNewKeyValue(e.target.value)} placeholder="Leave empty to auto-generate" />
            </div>

            <div className="text-xs text-sre-text-muted">
              <strong>Note:</strong> This key is intended to be shared locally (on-premise) and is not the OTEL agent auth token. Your OTEL agent requires an OTLP auth token (e.g., <code>otel_auth_token</code>), which will be mapped to this API key.
            </div>

            <div className="flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setShowAddModal(false)}>Cancel</Button>
              <Button type="submit" loading={loading}>Create</Button>
            </div>
          </form>
        </Modal>

        {/* YAML modal */}
        <Modal isOpen={showYamlModal} onClose={() => setShowYamlModal(false)} title="Generate OTEL Agent YAML" size="lg" closeOnOverlayClick={false}>
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <div className="flex items-center justify-between">
                  <label className="block text-sm font-medium text-sre-text mb-2">Select API Key</label>
                  <HelpTooltip text="Select the product or team this agent represents." />
                </div>
                <Select value={yamlModalKeyId} onChange={(e) => setYamlModalKeyId(e.target.value)} className="w-full">
                  {apiKeys.map((k) => (
                    <option key={k.id} value={k.id}>{k.name} {k.is_default ? '(Default)' : ''}</option>
                  ))}
                </Select>
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="block text-sm font-medium text-sre-text mb-2">OTLP Gateway Host</label>
                  <HelpTooltip text="Enter the gateway host only. Endpoints are derived automatically." />
                </div>
                <Input
                  value={gatewayHost}
                  onChange={(e) => setGatewayHost(e.target.value)}
                  placeholder={OTLP_GATEWAY_HOST}
                />
                <p className="text-xs text-sre-text-muted mt-1">Gateway host URL for OTLP endpoints.</p>
              </div>

              <div className="col-span-2">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-sre-text mb-2">OTLP Token</div>
                  <HelpTooltip text="This token will be sent as the 'x-otlp-token' HTTP header by exporters. Keep it secret." />
                </div>

                <div className="mt-1 p-2 bg-sre-background border border-sre-border rounded flex items-center justify-between gap-3">
                  <div className="font-mono text-xs truncate break-words">
                    {isYamlKeyShared
                      ? 'OTLP token not available for shared keys'
                      : (yamlModalToken
                        ? (yamlShowToken ? yamlModalToken : `${yamlModalToken.slice(0, 6)}...${yamlModalToken.slice(-4)}`)
                        : 'No token available')}
                  </div>
                  <div className="flex items-center gap-2">
                    {!isYamlKeyShared && (
                      <>
                        <Button size="sm" variant="ghost" onClick={() => setYamlShowToken(!yamlShowToken)} aria-label={yamlShowToken ? 'Hide token' : 'Show token'}>
                          {yamlShowToken ? 'Hide' : 'Show'}
                        </Button>
                        <Button size="sm" variant="secondary" onClick={() => handleCopy(yamlModalToken || '', 'OTLP token copied to clipboard')} aria-label="Copy OTLP token">Copy</Button>
                      </>
                    )}
                    {isYamlKeyShared && (
                      <div className="text-xs text-sre-text-muted">Token hidden — contact owner to obtain agent config.</div>
                    )}
                  </div>
                </div>

                <div className="text-xs text-sre-text-muted mt-2">Secure OTLP Gateway: the gateway validates the token and maps it to the tenant (X-Scope-OrgID). Do not expose raw org keys.</div>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Button variant="secondary" onClick={() => handleCopy(yamlModalContent, 'OTEL YAML copied to clipboard')} aria-label="Copy YAML" disabled={isYamlKeyShared}>
                <span className="material-icons mr-2">content_copy</span>Copy YAML
              </Button>
              <Button variant="secondary" onClick={() => handleDownloadYaml(yamlModalContent)} aria-label="Download YAML" disabled={isYamlKeyShared}>
                <span className="material-icons mr-2">download</span>Download YAML
              </Button>
              <div className="text-xs text-sre-text-muted ml-auto">sudo otelcol-contrib --config otel.yaml</div>
            </div>

            <div className="bg-sre-background p-3 rounded border border-sre-border text-xs overflow-auto max-h-72">
              <pre className="whitespace-pre-wrap break-words text-sre-text"><code>{yamlModalContent}</code></pre>
            </div>
          </div>
        </Modal>

        <Modal isOpen={showShareModal} onClose={() => { setShowShareModal(false); setSelectedShareGroupIds([]) }} title={`Share API Key${keyToShare ? `: ${keyToShare.name}` : ''}`} size="lg" closeOnOverlayClick={false}>
          <div className="space-y-4">
            <div className="text-xs text-sre-text-muted">Select users who can view and use this key. Owner retains edit/delete control.</div>
            <div className="p-3 rounded border border-sre-border bg-sre-background">
              <div className="text-xs font-medium text-sre-text mb-2">Share with groups you are in</div>
              {myShareableGroups.length > 0 ? (
                <div className="space-y-2 max-h-32 overflow-auto">
                  {myShareableGroups.map((group) => (
                    <div key={group.id} className="flex items-center justify-between p-2 rounded hover:bg-sre-surface/50">
                      <div className="text-sm text-sre-text">{group.name}</div>
                      <Checkbox
                        checked={selectedShareGroupIds.includes(group.id)}
                        onChange={() => setSelectedShareGroupIds((prev) => prev.includes(group.id) ? prev.filter((id) => id !== group.id) : [...prev, group.id])}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-sre-text-muted">No eligible groups found.</div>
              )}
            </div>
            <Input value={shareSearch} className="text-sm" onChange={(e) => setShareSearch(e.target.value)} placeholder="Search by username or email" />

            <div className="max-h-64 overflow-auto ">
              {filteredShareUsers
                .filter((u) => u.id !== user?.id)
                .map((u) => (
                  <div key={u.id} className="flex items-center justify-between p-2 rounded hover:bg-sre-surface/50">
                    <div className="text-sm text-sre-text">{u.username} {u.email ? `<${u.email}>` : ''}</div>
                    <Checkbox
                      checked={selectedShareUserIds.includes(u.id)}
                      onChange={() => setSelectedShareUserIds((prev) => prev.includes(u.id) ? prev.filter((id) => id !== u.id) : [...prev, u.id])}
                    />
                  </div>
                ))}
              {filteredShareUsers.filter((u) => u.id !== user?.id).length === 0 && (
                <div className="p-2 text-sm text-sre-text-muted">No users found.</div>
              )}
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => { setShowShareModal(false); setSelectedShareGroupIds([]) }}>Cancel</Button>
              <Button onClick={handleSaveShares} loading={loading}>Save</Button>
            </div>
          </div>
        </Modal>
      </div>
    </div>
  )
}
