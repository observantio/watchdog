import { useState, useEffect, useMemo } from 'react'

import {
  getAlerts, getSilences, createSilence, deleteSilence,
  getAlertRules, createAlertRule, updateAlertRule, deleteAlertRule,
  getNotificationChannels, createNotificationChannel, updateNotificationChannel,
  deleteNotificationChannel, testNotificationChannel, testAlertRule
} from '../api'
import { Card, Button, Select, Alert, Badge, Spinner, ConfirmDialog } from '../components/ui'
import RuleEditor from '../components/alertmanager/RuleEditor'
import ChannelEditor from '../components/alertmanager/ChannelEditor'
import SilenceForm from '../components/alertmanager/SilenceForm'

function normalizeChannelPayload(channelData) {
  const normalized = { ...channelData, config: channelData.config || {} }

  const mappings = {
    email: { smtpHost: 'smtp_host', smtpPort: 'smtp_port' },
    slack: { webhookUrl: 'webhook_url' },
    teams: { webhookUrl: 'webhook_url' },
    pagerduty: { integrationKey: 'routing_key' },
    opsgenie: { apiKey: 'api_key', apiUrl: 'api_url' }
  }

  const map = mappings[normalized.type]
  if (map) {
    for (const [from, to] of Object.entries(map)) {
      if (normalized.config[from] && !normalized.config[to]) {
        normalized.config[to] = normalized.config[from]
      }
    }
  }

  return normalized
}

export default function AlertManagerPage() {
  const [activeTab, setActiveTab] = useState('alerts')
  const [alerts, setAlerts] = useState([])
  const [silences, setSilences] = useState([])
  const [rules, setRules] = useState([])
  const [channels, setChannels] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showRuleEditor, setShowRuleEditor] = useState(false)
  const [showChannelEditor, setShowChannelEditor] = useState(false)
  const [showSilenceForm, setShowSilenceForm] = useState(false)
  const [editingRule, setEditingRule] = useState(null)
  const [editingChannel, setEditingChannel] = useState(null)
  const [filterSeverity, setFilterSeverity] = useState('all')
  const [confirmDialog, setConfirmDialog] = useState({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: null,
    confirmText: 'Delete',
    variant: 'danger'
  })

  const [testDialog, setTestDialog] = useState({ isOpen: false, title: '', message: '' })

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      const [alertsData, silencesData, rulesData, channelsData] = await Promise.all([
        getAlerts().catch(() => []),
        getSilences().catch(() => []),
        getAlertRules().catch(() => []),
        getNotificationChannels().catch(() => [])
      ])
      setAlerts(alertsData)
      setSilences(silencesData)
      setRules(rulesData)
      setChannels(channelsData)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  async function handleSaveRule(ruleData) {
    try {
      if (editingRule) {
        await updateAlertRule(editingRule.id, ruleData)
      } else {
        await createAlertRule(ruleData)
      }
      await loadData()
      setShowRuleEditor(false)
      setEditingRule(null)
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleDeleteRule(ruleId) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Alert Rule',
      message: 'Are you sure you want to delete this rule? This action cannot be undone.',
      confirmText: 'Delete',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await deleteAlertRule(ruleId)
          await loadData()
          setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null, confirmText: 'Delete', variant: 'danger' })
        } catch (e) {
          setError(e.message)
          setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null, confirmText: 'Delete', variant: 'danger' })
        }
      }
    })
  }

  async function handleSaveChannel(channelData) {
    try {
      const normalizedChannel = normalizeChannelPayload(channelData)
      if (editingChannel) {
        await updateNotificationChannel(editingChannel.id, normalizedChannel)
      } else {
        await createNotificationChannel(normalizedChannel)
      }
      await loadData()
      setShowChannelEditor(false)
      setEditingChannel(null)
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleDeleteChannel(channelId) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Notification Channel',
      message: 'Are you sure you want to delete this channel? This action cannot be undone.',
      confirmText: 'Delete',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await deleteNotificationChannel(channelId)
          await loadData()
          setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null, confirmText: 'Delete', variant: 'danger' })
        } catch (e) {
          setError(e.message)
          setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null, confirmText: 'Delete', variant: 'danger' })
        }
      }
    })
  }

  async function handleTestChannel(channelId) {
    try {
      const result = await testNotificationChannel(channelId)
      setTestDialog({ isOpen: true, title: 'Test Notification', message: result.message || 'Test notification sent' })
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleTestRule(ruleId) {
    try {
      const result = await testAlertRule(ruleId)
      setTestDialog({ isOpen: true, title: 'Success', message: result.message || 'We have invoked a test alert, please check your alerting system.' })
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleCreateSilence(silenceData) {
    try {
      await createSilence(silenceData)
      await loadData()
      setShowSilenceForm(false)
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleDeleteSilence(silenceId) {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete Silence',
      message: 'Are you sure you want to delete this silence?',
      confirmText: 'Delete',
      variant: 'danger',
      onConfirm: async () => {
        try {
          await deleteSilence(silenceId)
          await loadData()
          setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null, confirmText: 'Delete', variant: 'danger' })
        } catch (e) {
          setError(e.message)
          setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null, confirmText: 'Delete', variant: 'danger' })
        }
      }
    })
  }

  const filteredAlerts = useMemo(() => {
    if (filterSeverity === 'all') return alerts
    return alerts.filter(a => a.labels?.severity === filterSeverity)
  }, [alerts, filterSeverity])

  const stats = useMemo(() => ({
    totalAlerts: alerts.length,
    critical: alerts.filter(a => a.labels?.severity === 'critical').length,
    warning: alerts.filter(a => a.labels?.severity === 'warning').length,
    activeSilences: silences.length,
    enabledRules: rules.filter(r => r.enabled).length,
    totalRules: rules.length,
    enabledChannels: channels.filter(c => c.enabled).length,
    totalChannels: channels.length
  }), [alerts, silences, rules, channels])

  return (
    <div className="animate-fade-in">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-sre-text mb-2 flex items-center gap-2">
          <span className="material-icons text-3xl text-sre-primary">notifications_active</span>{' '}
          AlertManager
        </h1>
        <p className="text-sre-text-muted">Comprehensive alerting system with rules, channels, and silences</p>
      </div>

      {error && (
        <Alert variant="error" className="mb-6" onClose={() => setError(null)}>
          <strong>Error:</strong> {error}
        </Alert>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Card className="p-4">
          <div className="text-sre-text-muted text-xs mb-1">Active Alerts</div>
          <div className="text-2xl font-bold text-sre-text">{stats.totalAlerts}</div>
          <div className="text-xs text-sre-text-muted mt-1">
            <span className="text-red-500">{stats.critical} critical</span> · <span className="text-yellow-500">{stats.warning} warning</span>
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-sre-text-muted text-xs mb-1">Alert Rules</div>
          <div className="text-2xl font-bold text-sre-text">{stats.enabledRules}/{stats.totalRules}</div>
          <div className="text-xs text-sre-text-muted mt-1">enabled</div>
        </Card>
        <Card className="p-4">
          <div className="text-sre-text-muted text-xs mb-1">Notification Channels</div>
          <div className="text-2xl font-bold text-sre-text">{stats.enabledChannels}/{stats.totalChannels}</div>
          <div className="text-xs text-sre-text-muted mt-1">active</div>
        </Card>
        <Card className="p-4">
          <div className="text-sre-text-muted text-xs mb-1">Active Silences</div>
          <div className="text-2xl font-bold text-sre-text">{stats.activeSilences}</div>
          <div className="text-xs text-sre-text-muted mt-1">muting alerts</div>
        </Card>
      </div>

      <div className="mb-6 flex gap-2 border-b border-sre-border">
        {[
          { key: 'alerts', label: 'Alerts', icon: 'notification_important' },
          { key: 'rules', label: 'Rules', icon: 'rule' },
          { key: 'channels', label: 'Channels', icon: 'send' },
          { key: 'silences', label: 'Silences', icon: 'volume_off' }
        ].map(tab => (
          <button
            type="button"
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 flex items-center gap-2 border-b-2 transition-colors ${
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

      {loading ? (
        <div className="py-12">
          <Spinner size="lg" />
        </div>
      ) : (
        <>
          {activeTab === 'alerts' && (
            <Card 
              title="Active Alerts" 
              subtitle={`${filteredAlerts.length} alert${filteredAlerts.length === 1 ? '' : 's'}`}
              action={
                <Select value={filterSeverity} onChange={(e) => setFilterSeverity(e.target.value)}>
                  <option value="all">All Severities</option>
                  <option value="critical">Critical</option>
                  <option value="warning">Warning</option>
                  <option value="info">Info</option>
                </Select>
              }
            >
              {filteredAlerts.length ? (
                <div className="space-y-3">
                  {filteredAlerts.map((a, idx) => (
                    <div
                      key={a.fingerprint || a.id || a.starts_at || idx}
                      className="p-4 bg-sre-surface/50 border border-sre-border rounded-lg hover:border-sre-primary/30 transition-all"
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-3">
                          <span className="material-icons text-sre-error">
                            {a.labels?.severity === 'critical' ? 'error' : 'warning'}
                          </span>
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-sm font-semibold text-sre-text">
                                {a.labels?.alertname || 'Unknown'}
                              </span>
                              <Badge variant={a.labels?.severity === 'critical' ? 'error' : 'warning'}>
                                {a.labels?.severity || 'unknown'}
                              </Badge>
                              <Badge variant="default">{a.status?.state || 'active'}</Badge>
                            </div>
                            {a.annotations?.summary && (
                              <p className="text-sm text-sre-text-muted">{a.annotations.summary}</p>
                            )}
                          </div>
                        </div>
                        <span className="text-xs text-sre-text-muted">
                          {new Date(a.starts_at || a.startsAt).toLocaleString()}
                        </span>
                      </div>
                      {a.labels && Object.keys(a.labels).length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-1">
                          {Object.entries(a.labels)
                            .filter(([key]) => !['alertname', 'severity'].includes(key))
                            .map(([key, value]) => (
                              <span
                                key={key}
                                className="text-xs px-2 py-0.5 bg-sre-surface border border-sre-border rounded text-sre-text-muted"
                              >
                                {key}={value}
                              </span>
                            ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <span className="material-icons text-6xl text-sre-text-subtle mb-4">check_circle</span>
                  <p className="text-sre-text-muted">No active alerts</p>
                </div>
              )}
            </Card>
          )}

          {activeTab === 'rules' && (
            <>
              {showRuleEditor ? (
                <Card title={editingRule ? "Edit Alert Rule" : "Create Alert Rule"}>
                  <RuleEditor
                    rule={editingRule}
                    channels={channels}
                    onSave={handleSaveRule}
                    onCancel={() => {
                      setShowRuleEditor(false)
                      setEditingRule(null)
                    }}
                  />
                </Card>
              ) : (
                <Card
                  title="Alert Rules"
                  subtitle={`${rules.length} rule${rules.length === 1 ? '' : 's'} configured`}
                  action={
                    <Button onClick={() => setShowRuleEditor(true)}>
                      <span className="material-icons text-sm mr-2">add</span>{' '}Create Rule
                    </Button>
                  }
                >
                  {rules.length ? (
                    <div className="space-y-3">
                      {rules.map((rule) => {
                        let severityVariant;
                        if (rule.severity === 'critical') {
                          severityVariant = 'error';
                        } else if (rule.severity === 'warning') {
                          severityVariant = 'warning';
                        } else {
                          severityVariant = 'info';
                        }
                        return (
                        <div
                          key={rule.id}
                          className="p-4 bg-sre-surface/50 border border-sre-border rounded-lg hover:border-sre-primary/30 transition-all"
                        >
                          <div className="flex items-start justify-between mb-2">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="font-semibold text-sre-text">{rule.name}</span>
                                <Badge variant={severityVariant}>
                                  {rule.severity}
                                </Badge>
                                {rule.enabled ? (
                                  <Badge variant="success">Enabled</Badge>
                                ) : (
                                  <Badge variant="default">Disabled</Badge>
                                )}
                                <Badge variant="default">{rule.group}</Badge>
                              </div>
                              <p className="text-sm font-mono text-sre-text-muted mb-2">{rule.expr}</p>
                              <p className="text-xs text-sre-text-muted">
                                Duration: {rule.duration} · {rule.annotations?.summary || 'No summary'}
                              </p>
                            </div>
                            <div className="flex gap-2">
                              <Button variant="ghost" onClick={() => handleTestRule(rule.id)}>
                                <span className="material-icons text-sm">science</span>
                              </Button>
                              <Button
                                variant="ghost"
                                onClick={() => {
                                  setEditingRule(rule)
                                  setShowRuleEditor(true)
                                }}
                              >
                                <span className="material-icons text-sm">edit</span>
                              </Button>
                              <Button variant="ghost" onClick={() => handleDeleteRule(rule.id)}>
                                <span className="material-icons text-sm">delete</span>
                              </Button>
                            </div>
                          </div>
                        </div>
                        )
                      })}
                    </div>
                  ) : (
                    <div className="text-center py-12">
                      <span className="material-icons text-6xl text-sre-text-subtle mb-4">rule</span>
                      <p className="text-sre-text-muted mb-4">No alert rules configured</p>
                      <Button onClick={() => setShowRuleEditor(true)}>
                        <span className="material-icons text-sm mr-2">add</span>{' '}Create Your First Rule
                      </Button>
                    </div>
                  )}
                </Card>
              )}
            </>
          )}

          {activeTab === 'channels' && (
            <>
              {showChannelEditor ? (
                <Card title={editingChannel ? "Edit Notification Channel" : "Create Notification Channel"}>
                  <ChannelEditor
                    channel={editingChannel}
                    onSave={handleSaveChannel}
                    onCancel={() => {
                      setShowChannelEditor(false)
                      setEditingChannel(null)
                    }}
                  />
                </Card>
              ) : (
                <Card
                  title="Notification Channels"
                  subtitle={`${channels.length} channel${channels.length === 1 ? '' : 's'} configured`}
                  action={
                    <Button onClick={() => setShowChannelEditor(true)}>
                      <span className="material-icons text-sm mr-2">add</span>{' '}Create Channel
                    </Button>
                  }
                >
                  {channels.length ? (
                    <div className="space-y-3">
                      {channels.map((channel) => {
                        let iconName;
                        if (channel.type === 'email') {
                          iconName = 'email'
                        } else if (channel.type === 'slack') {
                          iconName = 'chat'
                        } else if (channel.type === 'teams') {
                          iconName = 'groups'
                        } else {
                          iconName = 'webhook'
                        }
                        return (
                        <div
                          key={channel.id}
                          className="p-4 bg-sre-surface/50 border border-sre-border rounded-lg hover:border-sre-primary/30 transition-all"
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="material-icons text-sre-primary">{iconName}</span>
                                <span className="font-semibold text-sre-text">{channel.name}</span>
                                <Badge variant="info">{channel.type}</Badge>
                                {channel.enabled ? (
                                  <Badge variant="success">Enabled</Badge>
                                ) : (
                                  <Badge variant="default">Disabled</Badge>
                                )}
                              </div>
                              <p className="text-xs text-sre-text-muted">
                                {channel.type === 'email' && `To: ${channel.config.to}`}
                                {channel.type === 'slack' && `Channel: ${channel.config.channel || 'default'}`}
                                {channel.type === 'webhook' && `URL: ${channel.config.url}`}
                              </p>
                            </div>
                            <div className="flex gap-2">
                              <Button variant="ghost" onClick={() => handleTestChannel(channel.id)}>
                                <span className="material-icons text-sm">send</span>
                              </Button>
                              <Button
                                variant="ghost"
                                onClick={() => {
                                  setEditingChannel(channel)
                                  setShowChannelEditor(true)
                                }}
                              >
                                <span className="material-icons text-sm">edit</span>
                              </Button>
                              <Button variant="ghost" onClick={() => handleDeleteChannel(channel.id)}>
                                <span className="material-icons text-sm">delete</span>
                              </Button>
                            </div>
                          </div>
                        </div>
                        )
                      })}
                    </div>
                  ) : (
                    <div className="text-center py-12">
                      <span className="material-icons text-6xl text-sre-text-subtle mb-4">send</span>
                      <p className="text-sre-text-muted mb-4">No notification channels configured</p>
                      <Button onClick={() => setShowChannelEditor(true)}>
                        <span className="material-icons text-sm mr-2">add</span>{' '}Create Your First Channel
                      </Button>
                    </div>
                  )}
                </Card>
              )}
            </>
          )}

          {activeTab === 'silences' && (
            <>
              {showSilenceForm ? (
                <Card title="Create Silence">
                  <SilenceForm
                    onSave={handleCreateSilence}
                    onCancel={() => setShowSilenceForm(false)}
                  />
                </Card>
              ) : (
                <Card
                  title="Active Silences"
                  subtitle={`${silences.length} silence${silences.length === 1 ? '' : 's'} active`}
                  action={
                    <Button onClick={() => setShowSilenceForm(true)}>
                      <span className="material-icons text-sm mr-2">add</span>{' '}Create Silence
                    </Button>
                  }
                >
                  {silences.length ? (
                    <div className="space-y-3">
                      {silences.map((s) => (
                        <div
                          key={s.id}
                          className="p-4 bg-sre-surface/50 border border-sre-border rounded-lg hover:border-sre-primary/30 transition-all"
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="material-icons text-sre-warning">volume_off</span>
                                <Badge variant="warning">Silenced</Badge>
                                <span className="text-sm text-sre-text-muted">{s.comment}</span>
                              </div>
                              <div className="text-xs text-sre-text-muted mb-2">
                                <span className="font-mono">ID: {s.id}</span>
                              </div>
                              {s.matchers && s.matchers.length > 0 && (
                                <div className="flex flex-wrap gap-1">
                                  {s.matchers.map((m) => (
                                    <span
                                      key={`${m.name}-${m.isEqual ? 'eq' : 'neq'}-${m.value}`}
                                      className="text-xs px-2 py-0.5 bg-sre-surface border border-sre-border rounded text-sre-text"
                                    >
                                      {m.name}{m.isEqual ? '=' : '!='}{m.value}
                                    </span>
                                  ))}
                                </div>
                              )}
                              <div className="text-xs text-sre-text-muted mt-2">
                                {new Date(s.starts_at || s.startsAt).toLocaleString()} → {new Date(s.ends_at || s.endsAt).toLocaleString()}
                              </div>
                            </div>
                            <Button variant="ghost" onClick={() => handleDeleteSilence(s.id)}>
                              <span className="material-icons text-sm">delete</span>
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-12">
                      <span className="material-icons text-6xl text-sre-text-subtle mb-4">volume_up</span>
                      <p className="text-sre-text-muted mb-4">No active silences</p>
                      <Button onClick={() => setShowSilenceForm(true)}>
                        <span className="material-icons text-sm mr-2">add</span>{' '}
                        Create Silence
                      </Button>
                    </div>
                  )}
                </Card>
              )}
            </>
          )}
        </>
      )}

      <ConfirmDialog
        isOpen={testDialog.isOpen}
        title={testDialog.title}
        message={testDialog.message}
        onConfirm={() => setTestDialog({ isOpen: false, title: '', message: '' })}
        confirmText="OK"
        variant="success"
        onClose={() => setTestDialog({ isOpen: false, title: '', message: '' })}
      />

      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        title={confirmDialog.title}
        message={confirmDialog.message}
        onConfirm={confirmDialog.onConfirm}
        confirmText={confirmDialog.confirmText}
        variant={confirmDialog.variant}
        onClose={() => setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null, confirmText: 'Delete', variant: 'danger' })}
      />
    </div>
  )
}
