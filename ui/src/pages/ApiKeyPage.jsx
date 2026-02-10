import { useState, useEffect, useMemo } from 'react'
import { Card, Input, Button, Alert, Select } from '../components/ui'
import { useAuth } from '../contexts/AuthContext'
import * as api from '../api'

const buildOtelYaml = (apiKey) => `receivers:
  hostmetrics:
    collection_interval: 1s
    scrapers:
      cpu:

  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
  
  resource:
    attributes:
      - key: tenant_id
        value: "${apiKey}"
        action: upsert

exporters:
  otlphttp/loki:
    endpoint: "http://loki:3100/otlp"
    headers:
      X-Scope-OrgID: "${apiKey}"
    tls:
      insecure: true
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 5m
    sending_queue:
      enabled: true
      num_consumers: 10
      queue_size: 1000

  otlp/tempo:
    endpoint: "tempo:4317"
    headers:
      X-Scope-OrgID: "${apiKey}"
    tls:
      insecure: true
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 5m
    sending_queue:
      enabled: true
      num_consumers: 10
      queue_size: 1000

  prometheusremotewrite/mimir:
    endpoint: "http://mimir:9009/api/v1/push"
    headers:
      X-Scope-OrgID: "${apiKey}"
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 5m

  debug:
    verbosity: normal

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [memory_limiter, resource]
      exporters: [otlphttp/loki, debug]

    traces:
      receivers: [otlp]
      processors: [memory_limiter, resource]
      exporters: [otlp/tempo, debug]

    metrics:
      receivers: [hostmetrics, otlp]
      processors: [memory_limiter, resource]
      exporters: [prometheusremotewrite/mimir, debug]

  telemetry:
    logs:
      level: info
`

export default function ApiKeyPage() {
  const { user, updateUser } = useAuth()
  const [orgId, setOrgId] = useState('')
  const [apiKeys, setApiKeys] = useState([])
  const [yamlKeyId, setYamlKeyId] = useState('')
  const [newKeyName, setNewKeyName] = useState('')
  const [newKeyValue, setNewKeyValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)
  const [showKeyId, setShowKeyId] = useState(null)

  useEffect(() => {
    if (user) {
      setApiKeys(user.api_keys || [])
      const enabled = (user.api_keys || []).filter((k) => k.is_enabled)
      const initialKey = enabled[0] || (user.api_keys || [])[0]
      setYamlKeyId(initialKey?.id || '')
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
    const enabled = (updatedUser.api_keys || []).filter((k) => k.is_enabled)
    const initialKey = enabled[0] || (updatedUser.api_keys || [])[0]
    setYamlKeyId(initialKey?.id || '')
  }

  const handleSaveOrgId = async (e) => {
    e.preventDefault()
    setError(null)
    setMessage(null)
    setLoading(true)
    try {
      if (!orgId) {
        setError('Please select an API key')
        setLoading(false)
        return
      }
      // Set the selected API key as the default key
      await api.updateApiKey(orgId, { is_default: true })
      await refreshUser()
      setMessage('Default API key updated successfully.')
    } catch (err) {
      setError(err.body?.detail || err.message || 'Failed to update default API key')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateKey = async (e) => {
    e.preventDefault()
    setError(null)
    setMessage(null)
    if (!newKeyName.trim()) {
      setError('Key name is required')
      return
    }
    setLoading(true)
    try {
      await api.createApiKey({ name: newKeyName.trim(), key: newKeyValue.trim() || undefined })
      setNewKeyName('')
      setNewKeyValue('')
      await refreshUser()
      setMessage('API key created successfully.')
    } catch (err) {
      setError(err.body?.detail || err.message || 'Failed to create API key')
    } finally {
      setLoading(false)
    }
  }

  const handleActivateKey = async (key) => {
    setError(null)
    setMessage(null)
    try {
      await api.updateApiKey(key.id, { is_enabled: true })
      await refreshUser()
    } catch (err) {
      setError(err.body?.detail || err.message || 'Failed to update API key')
    }
  }

  const handleDeleteKey = async (key) => {
    setError(null)
    setMessage(null)
    try {
      await api.deleteApiKey(key.id)
      await refreshUser()
      setMessage('API key deleted successfully.')
    } catch (err) {
      setError(err.body?.detail || err.message || 'Failed to delete API key')
    }
  }

  const handleCopy = async (value, successMessage) => {
    try {
      await navigator.clipboard.writeText(value)
      setMessage(successMessage)
    } catch (err) {
      console.error('Copy to clipboard failed:', err)
      setError('Failed to copy to clipboard')
    }
  }

  const handleDownloadYaml = (content) => {
    const blob = new Blob([content], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'otel-agent.yaml'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  const yamlKey = useMemo(() => apiKeys.find((k) => k.id === yamlKeyId) || apiKeys[0], [apiKeys, yamlKeyId])
  const selectedOrgKeyValue = useMemo(() => {
    const found = apiKeys.find((k) => k.id === orgId)
    return found?.key || user?.org_id || ''
  }, [apiKeys, orgId, user])
  const yamlContent = useMemo(() => buildOtelYaml(yamlKey?.key || selectedOrgKeyValue || ''), [yamlKey, selectedOrgKeyValue])

  const enabledCount = apiKeys.filter((k) => k.is_enabled).length

  return (
    <div className="animate-fade-in max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-3xl font-semibold text-sre-text mb-2 flex items-center gap-3">
          <span className="material-icons text-sre-primary text-3xl">key</span>
          <span>API Keys</span>
        </h1>
        <p className="text-sre-text-muted max-w-2xl">Manage tenant keys for logs, traces and metrics. Use keys to isolate datasets per product or team.</p>
      </div>

      {message && (
        <Alert variant="success" className="mb-6">
          {message}
        </Alert>
      )}

      {error && (
        <Alert variant="error" className="mb-6">
          <strong>Error:</strong> {error}
        </Alert>
      )}

      <div className="space-y-8">
        <div className="grid gap-6 md:grid-cols-2">
          <Card title="Default API Key" subtitle="Default tenant identifier used by public agents" className="p-4 border border-sre-border rounded-lg shadow-sm bg-sre-surface">
            <form onSubmit={handleSaveOrgId} className="flex gap-3 items-start">
              <Select
                value={orgId}
                onChange={(e) => setOrgId(e.target.value)}
                aria-label="Default API key select"
                className="min-w-[240px]"
                required
              >
                {apiKeys.length === 0 ? (
                  <option value="">No API keys available</option>
                ) : (
                  apiKeys.map((k) => (
                    <option key={k.id} value={k.id}>
                      {k.name} {k.is_default ? '(Default)' : ''}
                    </option>
                  ))
                )}
              </Select>
              <div className="flex flex-col gap-2">
                <Button type="submit" loading={loading} disabled={apiKeys.length === 0} className="whitespace-nowrap">Save</Button>
              </div>
            </form>
          </Card>

          <Card title="Add API Key" subtitle="Create a new tenant key or save an existing one" className="p-4 border border-sre-border rounded-lg shadow-sm bg-sre-surface">
            <form onSubmit={handleCreateKey} className="grid gap-4">
              <Input
                label="Key Name"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                placeholder="e.g., XYZ Product"
                required
              />
              <Input
                label="Key Value (optional)"
                value={newKeyValue}
                onChange={(e) => setNewKeyValue(e.target.value)}
                placeholder="Leave empty to auto-generate"
              />
              <div className="flex justify-end">
                <Button type="submit" loading={loading}>Add Key</Button>
              </div>
            </form>
          </Card>
        </div>

        <Card title={`API Keys (${apiKeys.length})`} subtitle={`Enabled: ${enabledCount}`} className="p-4 rounded-lg border border-sre-border shadow-sm bg-sre-surface">
          {apiKeys.length === 0 ? (
            <div className="p-4 text-sm text-sre-text-muted">No API keys found.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="bg-sre-surface text-sre-text-muted text-xs uppercase tracking-wide">
                    <th className="py-3 px-4">Name</th>
                    <th className="py-3 px-4">Key</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {apiKeys.map((key) => (
                    <tr key={key.id} className="align-top hover:bg-sre-background">
                      <td className="py-3 px-4">
                        <div className="font-medium text-sre-text">{key.name}</div>
                        {key.is_default && <div className="text-xs text-sre-text-muted">Default</div>}
                      </td>
                      <td className="py-3 px-4 text-xs text-sre-text-muted break-all">
                        <div className="flex items-center gap-3">
                          <div className="font-mono text-xs">
                            {(() => {
                              let displayKey;
                              if (showKeyId === key.id) {
                                displayKey = key.key;
                              } else if (key.key) {
                                displayKey = `${key.key.slice(0, 6)}...${key.key.slice(-4)}`;
                              } else {
                                displayKey = '-';
                              }
                              return displayKey;
                            })()}
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
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          {!key.is_default && (
                            <Button size="sm" variant="danger" onClick={() => handleDeleteKey(key)}>Delete</Button>
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

        <Card title="OTEL Agent YAML" className="p-4 mt-6 border border-sre-border rounded-lg shadow-sm bg-sre-surface" subtitle="Prefilled configuration for your agent">
          <div className="space-y-3">
            <Select
              label="Select API Key for Agent"
              value={yamlKeyId}
              onChange={(e) => setYamlKeyId(e.target.value)}
            >
              {apiKeys.map((key) => (
                <option key={key.id} value={key.id}>
                  {key.name} {key.is_default ? '(Default)' : ''}
                </option>
              ))}
            </Select>

            <div className="flex gap-3 items-center">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleCopy(yamlContent, 'OTEL YAML copied to clipboard')}
                aria-label="Copy YAML"
                title="Copy YAML"
              >
                <span className="material-icons">content_copy</span>
              </Button>

              <Button
                variant="secondary"
                size="sm"
                onClick={() => handleDownloadYaml(yamlContent)}
                aria-label="Download YAML"
                title="Download YAML"
              >
                <span className="material-icons">download</span>
              </Button>
            </div>

            <div className="bg-sre-background p-3 rounded border border-sre-border text-xs overflow-auto max-h-72">
              <pre className="whitespace-pre-wrap break-words text-sre-text"><code>{yamlContent}</code></pre>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
