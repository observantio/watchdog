import { useState, useEffect, useMemo } from 'react'

import {
  getAlerts, getSilences, createSilence, deleteSilence,
  getAlertRules, createAlertRule, updateAlertRule, deleteAlertRule,
  getNotificationChannels, createNotificationChannel, updateNotificationChannel,
  deleteNotificationChannel, testNotificationChannel, testAlertRule
} from '../api'
import { Card, Button, Select, Alert, Badge, Spinner, Modal } from '../components/ui'
import ConfirmModal from '../components/ConfirmModal'
import HelpTooltip from '../components/HelpTooltip'
import RuleEditor from '../components/alertmanager/RuleEditor'
import ChannelEditor from '../components/alertmanager/ChannelEditor'
import SilenceForm from '../components/alertmanager/SilenceForm'
import { ALERT_SEVERITY_OPTIONS } from '../utils/constants'
import { useAuth } from '../contexts/AuthContext'

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

const EMPTY_CONFIRM = { isOpen: false, title: '', message: '', onConfirm: null, confirmText: 'Delete', variant: 'danger' }

export default function AlertManagerPage() {
  const { user } = useAuth()
  const apiKeys = user?.api_keys || []
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
  const [confirmDialog, setConfirmDialog] = useState(EMPTY_CONFIRM)

  const [testDialog, setTestDialog] = useState({ isOpen: false, title: '', message: '' })

  const defaultMetricKeys = ['activeAlerts','alertRules','channels','silences']
  const [metricOrder, setMetricOrder] = useState(() => {
    try {
      const raw = localStorage.getItem('alertmanager-metric-order')
      if (!raw) return defaultMetricKeys
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return defaultMetricKeys
      const setp = new Set(parsed)
      if (!defaultMetricKeys.every(k => setp.has(k))) return defaultMetricKeys
      return parsed
    } catch (e) {
      return defaultMetricKeys
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem('alertmanager-metric-order', JSON.stringify(metricOrder))
    } catch (e) {
      // Silently handle localStorage failure
    }
  }, [metricOrder])

  function handleApiError(e) {
    if (!e) return
    if (e.status === 403) return
    if (e.message?.includes('Error sending test notification')) return
    setError(e.message || String(e))
  }

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
      handleApiError(e)
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
      return true
    } catch (e) {
      handleApiError(e)
      return false
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
          setConfirmDialog(EMPTY_CONFIRM)
        } catch (e) {
          handleApiError(e)
          setConfirmDialog(EMPTY_CONFIRM)
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
      handleApiError(e)
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
          setConfirmDialog(EMPTY_CONFIRM)
        } catch (e) {
          handleApiError(e)
          setConfirmDialog(EMPTY_CONFIRM)
        }
      }
    })
  }

  async function handleTestChannel(channelId) {
    try {
      const result = await testNotificationChannel(channelId)
      setTestDialog({ isOpen: true, title: 'Test Notification', message: result.message || 'Test notification sent' })
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleTestRule(ruleId) {
    try {
      const result = await testAlertRule(ruleId)
      setTestDialog({ isOpen: true, title: 'Success', message: result.message || 'We have invoked a test alert, please check your alerting system.' })
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleCreateSilence(silenceData) {
    try {
      await createSilence(silenceData)
      await loadData()
      setShowSilenceForm(false)
    } catch (e) {
      handleApiError(e)
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
          setConfirmDialog(EMPTY_CONFIRM)
        } catch (e) {
          handleApiError(e)
          setConfirmDialog(EMPTY_CONFIRM)
        }
      }
    })
  }

  const filteredAlerts = useMemo(() => {
    if (filterSeverity === 'all') return alerts
    return alerts.filter(a => a.labels?.severity === filterSeverity)
  }, [alerts, filterSeverity])

  // Map org_id (API key value) → key name for display in rules list
  const orgIdToName = useMemo(() => {
    const map = {}
    for (const k of apiKeys) {
      if (k.key) map[k.key] = k.name
    }
    return map
  }, [apiKeys])

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

      {/* Draggable Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {metricOrder.map((key) => {
          const metricData = {
            activeAlerts: { label: 'Active Alerts', value: stats.totalAlerts, detail: <><span className="text-red-500">{stats.critical} critical</span> · <span className="text-yellow-500">{stats.warning} warning</span></> },
            alertRules: { label: 'Alert Rules', value: `${stats.enabledRules}/${stats.totalRules}`, detail: 'enabled' },
            channels: { label: 'Notification Channels', value: `${stats.enabledChannels}/${stats.totalChannels}`, detail: 'active' },
            silences: { label: 'Active Silences', value: stats.activeSilences, detail: 'muting alerts' },
          }[key]

          return (
            <div
              key={key}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.effectAllowed = 'move'
                e.dataTransfer.setData('text/plain', key)
                e.currentTarget.classList.add('opacity-50', 'scale-95')
              }}
              onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move' }}
              onDrop={(e) => {
                e.preventDefault()
                try {
                  const sourceKey = e.dataTransfer.getData('text/plain')
                  if (!sourceKey || sourceKey === key) return
                  const next = [...metricOrder]
                  const fromIdx = next.indexOf(sourceKey)
                  const toIdx = next.indexOf(key)
                  if (fromIdx === -1 || toIdx === -1) return
                  next[fromIdx] = key
                  next[toIdx] = sourceKey
                  setMetricOrder(next)
                } catch { /* ignore */ }
              }}
              onDragEnd={(e) => { e.currentTarget.classList.remove('opacity-50', 'scale-95') }}
              title="Drag to rearrange"
              className="cursor-move transition-transform duration-200 ease-out will-change-transform"
            >
              <Card className="p-4 relative overflow-visible bg-gradient-to-br from-sre-surface to-sre-surface/80 border-2 border-sre-border/50 hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm">
                <div className="absolute top-2 right-2 text-sre-text-muted hover:text-sre-text transition-colors">
                  <span className="material-icons text-sm drag-handle" aria-hidden>drag_indicator</span>
                </div>
                <div className="text-sre-text-muted text-xs mb-1">{metricData.label}</div>
                <div className="text-2xl font-bold text-sre-text">{metricData.value}</div>
                <div className="text-xs text-sre-text-muted mt-1">{metricData.detail}</div>
              </Card>
            </div>
          )
        })}
      </div>

      <div className="mb-6 flex gap-2 border-b border-sre-border justify-center items-center">
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
            className={`pl-4 pr-4 py-2 flex items-center justify-center gap-2 border-b-2 transition-colors ${
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
            <>
                <div className="space-y-6">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="material-icons text-2xl text-sre-primary">warning</span>
                      <div>
                        <h2 className="text-xl font-semibold text-sre-text">Active Alerts</h2>
                        <p className="text-sm text-sre-text-muted">
                          {filteredAlerts.length > 0
                            ? `You've got ${filteredAlerts.length} alert${filteredAlerts.length !== 1 ? 's' : ''} firing`
                            : 'No active alerts'
                          }
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Select value={filterSeverity} onChange={(e) => setFilterSeverity(e.target.value)}>
                        {ALERT_SEVERITY_OPTIONS.map(opt => (
                          <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                      </Select>
                      <HelpTooltip text="Filter alerts by severity level. Choose 'All' to see all alerts, or select specific severity to focus on critical or warning alerts." />
                    </div>
                  </div>

                  {filteredAlerts.length > 0 ? (
                    <div className="space-y-4">
                      {filteredAlerts.map((a, idx) => (
                        <div
                          key={a.fingerprint || a.id || a.starts_at || idx}
                          className="p-6 bg-sre-surface border-2 border-sre-border rounded-xl hover:border-sre-primary/50 hover:shadow-md transition-all duration-200"
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-3 mb-3">
                                <div className={`p-2 rounded-lg ${
                                  a.labels?.severity === 'critical'
                                    ? 'bg-red-100 dark:bg-red-900/30'
                                    : 'bg-yellow-100 dark:bg-yellow-900/30'
                                }`}>
                                  <span className={`material-icons text-xl ${
                                    a.labels?.severity === 'critical'
                                      ? 'text-red-600 dark:text-red-400'
                                      : 'text-yellow-600 dark:text-yellow-400'
                                  }`}>
                                    {a.labels?.severity === 'critical' ? 'error' : 'warning'}
                                  </span>
                                </div>
                                <div>
                                  <h3 className="font-semibold text-sre-text text-lg">{a.labels?.alertname || 'Unknown'}</h3>
                                  <div className="flex items-center gap-2 mt-1">
                                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                                      a.labels?.severity === 'critical'
                                        ? 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200'
                                        : 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-200'
                                    }`}>
                                      {a.labels?.severity || 'unknown'}
                                    </span>
                                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                                      a.status?.state === 'active'
                                        ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200'
                                        : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'
                                    }`}>
                                      {a.status?.state || 'active'}
                                    </span>
                                  </div>
                                </div>
                              </div>

                              {a.annotations?.summary && (
                                <p className="text-sm text-sre-text-muted mb-3">{a.annotations.summary}</p>
                              )}

                              {a.labels && Object.keys(a.labels).length > 0 && (
                                <div className="flex flex-wrap gap-2">
                                  {Object.entries(a.labels)
                                    .filter(([key]) => !['alertname', 'severity'].includes(key))
                                    .map(([key, value]) => (
                                      <span
                                        key={key}
                                        className="text-xs px-3 py-1 bg-sre-bg-alt border border-sre-border rounded-full text-sre-text-muted"
                                      >
                                        {key}={value}
                                      </span>
                                    ))}
                                </div>
                              )}
                            </div>

                            <div className="flex flex-col items-end gap-2 ml-4">
                              <span className="text-xs text-sre-text-muted whitespace-nowrap">
                                {new Date(a.starts_at || a.startsAt).toLocaleString()}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
                      <span className="material-icons text-5xl text-sre-text-muted mb-4 block">check_circle</span>
                      <h3 className="text-xl font-semibold text-sre-text mb-2">No Active Alerts</h3>
                      <p className="text-sre-text-muted mb-6 max-w-md mx-auto">
                        All systems are running smoothly. No alerts are currently firing.
                      </p>
                    </div>
                  )}
                </div>
            </>
          )}

          {activeTab === 'rules' && (
            <>
                <div className="space-y-6">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="material-icons text-2xl text-sre-primary">rule</span>
                      <div>
                        <h2 className="text-xl font-semibold text-sre-text">Alert Rules</h2>
                        <p className="text-sm text-sre-text-muted">
                          {rules.length > 0
                            ? `${rules.length} rule${rules.length !== 1 ? 's' : ''} configured`
                            : 'No rules configured'
                          }
                        </p>
                      </div>
                    </div>
                    {rules.length > 0 && (
                      <Button onClick={() => { setEditingRule(null); setShowRuleEditor(true); }}>
                        <span className="material-icons text-sm mr-2">add</span>
                        Create Rule
                      </Button>
                    )}
                  </div>

                  {rules.length > 0 ? (
                    <div className="grid gap-4">
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
                            className="p-6 bg-sre-surface border-2 border-sre-border rounded-xl hover:border-sre-primary/50 hover:shadow-md transition-all duration-200"
                          >
                            <div className="flex items-start justify-between">
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-3 mb-3">
                                  <div className={`p-2 rounded-lg ${
                                    rule.severity === 'critical'
                                      ? 'bg-red-100 dark:bg-red-900/30'
                                      : rule.severity === 'warning'
                                      ? 'bg-yellow-100 dark:bg-yellow-900/30'
                                      : 'bg-blue-100 dark:bg-blue-900/30'
                                  }`}>
                                    <span className={`material-icons text-xl ${
                                      rule.severity === 'critical'
                                        ? 'text-red-600 dark:text-red-400'
                                        : rule.severity === 'warning'
                                        ? 'text-yellow-600 dark:text-yellow-400'
                                        : 'text-blue-600 dark:text-blue-400'
                                    }`}>
                                      {rule.severity === 'critical' ? 'error' : rule.severity === 'warning' ? 'warning' : 'info'}
                                    </span>
                                  </div>
                                  <div>
                                    <h3 className="font-semibold text-sre-text text-lg">{rule.name}</h3>
                                    <div className="flex items-center gap-2 mt-1">
                                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                                        rule.severity === 'critical'
                                          ? 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200'
                                          : rule.severity === 'warning'
                                          ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-200'
                                          : 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200'
                                      }`}>
                                        {rule.severity}
                                      </span>
                                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                                        rule.enabled
                                          ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200'
                                          : 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200'
                                      }`}>
                                        {rule.enabled ? 'Enabled' : 'Disabled'}
                                      </span>
                                      <span className="px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200">
                                        {rule.group}
                                      </span>
                                      {rule.orgId ? (
                                        <span className="px-2 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-200">
                                          {orgIdToName[rule.orgId] || `${rule.orgId.slice(0, 8)}...`}
                                        </span>
                                      ) : (
                                        <span className="px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200">
                                          All products
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                </div>

                                <div className="space-y-2 text-sm text-sre-text-muted">
                                  <div className="flex items-center gap-2">
                                    <span className="material-icons text-sm">functions</span>
                                    <span className="font-mono text-xs bg-sre-bg-alt px-2 py-1 rounded border">{rule.expr}</span>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <span className="material-icons text-sm">schedule</span>
                                    <span>Duration: {rule.duration}</span>
                                  </div>
                                  {rule.annotations?.summary && (
                                    <div className="flex items-start gap-2">
                                      <span className="material-icons text-sm mt-0.5">description</span>
                                      <span>{rule.annotations.summary}</span>
                                    </div>
                                  )}
                                </div>
                              </div>

                              <div className="flex gap-1 ml-4">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleTestRule(rule.id)}
                                  className="p-2"
                                  title="Test Rule"
                                >
                                  <span className="material-icons text-base">science</span>
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => {
                                    setEditingRule(rule)
                                    setShowRuleEditor(true)
                                  }}
                                  className="p-2"
                                  title="Edit Rule"
                                >
                                  <span className="material-icons text-base">edit</span>
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleDeleteRule(rule.id)}
                                  className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-900/20"
                                  title="Delete Rule"
                                >
                                  <span className="material-icons text-base">delete</span>
                                </Button>
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
                      <span className="material-icons text-5xl text-sre-text-muted mb-4 block">rule</span>
                      <h3 className="text-xl font-semibold text-sre-text mb-2">No Rules Configured</h3>
                      <p className="text-sre-text-muted mb-6 max-w-md mx-auto">
                        Create alert rules to monitor your systems and get notified when issues occur.
                      </p>
                      <Button onClick={() => { setEditingRule(null); setShowRuleEditor(true); }}>
                        <span className="material-icons text-sm mr-2">add</span>
                        Create Your First Rule
                      </Button>
                    </div>
                  )}
                </div>
            </>
          )}

          {activeTab === 'channels' && (
            <>
                <div className="space-y-6">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="material-icons text-2xl text-sre-primary">notifications</span>
                      <div>
                        <h2 className="text-xl font-semibold text-sre-text">Notification Channels</h2>
                        <p className="text-sm text-sre-text-muted">
                          {channels.length > 0
                            ? `${channels.length} channel${channels.length !== 1 ? 's' : ''} configured`
                            : 'No channels configured'
                          }
                        </p>
                      </div>
                    </div>
                    {channels.length > 0 && (
                      <Button onClick={() => { setEditingChannel(null); setShowChannelEditor(true); }}>
                        <span className="material-icons text-sm mr-2">add</span>
                        Create Channel
                      </Button>
                    )}
                  </div>

                  {channels.length > 0 ? (
                    <div className="space-y-4">
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
                            className="p-6 bg-sre-surface border-2 border-sre-border rounded-xl hover:border-sre-primary/50 hover:shadow-md transition-all duration-200"
                          >
                            <div className="flex items-start justify-between">
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-3 mb-3">
                                  <div className={`p-2 rounded-lg ${
                                    channel.type === 'slack'
                                      ? 'bg-purple-100 dark:bg-purple-900/30'
                                      : channel.type === 'email'
                                      ? 'bg-blue-100 dark:bg-blue-900/30'
                                      : channel.type === 'webhook'
                                      ? 'bg-green-100 dark:bg-green-900/30'
                                      : channel.type === 'teams'
                                      ? 'bg-blue-100 dark:bg-blue-900/30'
                                      : 'bg-gray-100 dark:bg-gray-700'
                                  }`}>
                                    <span className={`material-icons text-xl ${
                                      channel.type === 'slack'
                                        ? 'text-purple-600 dark:text-purple-400'
                                        : channel.type === 'email'
                                        ? 'text-blue-600 dark:text-blue-400'
                                        : channel.type === 'webhook'
                                        ? 'text-green-600 dark:text-green-400'
                                        : channel.type === 'teams'
                                        ? 'text-blue-600 dark:text-blue-400'
                                        : 'text-gray-600 dark:text-gray-400'
                                    }`}>{iconName}</span>
                                  </div>
                                  <div>
                                    <h3 className="font-semibold text-sre-text text-lg">{channel.name}</h3>
                                    <div className="flex items-center gap-2 mt-1">
                                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                                        channel.type === 'slack'
                                          ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-200'
                                          : channel.type === 'email'
                                          ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200'
                                          : channel.type === 'webhook'
                                          ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200'
                                          : channel.type === 'teams'
                                          ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200'
                                          : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'
                                      }`}>
                                        {channel.type}
                                      </span>
                                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                                        channel.enabled
                                          ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200'
                                          : 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200'
                                      }`}>
                                        {channel.enabled ? 'Enabled' : 'Disabled'}
                                      </span>
                                    </div>
                                  </div>
                                </div>

                                <div className="space-y-2 text-sm text-sre-text-muted">
                                  {channel.type === 'email' && channel.config?.to && (
                                    <div className="flex items-center gap-2">
                                      <span className="material-icons text-sm">email</span>
                                      <span>To: {channel.config.to}</span>
                                    </div>
                                  )}
                                  {channel.type === 'slack' && channel.config?.channel && (
                                    <div className="flex items-center gap-2">
                                      <span className="material-icons text-sm">tag</span>
                                      <span>Channel: {channel.config.channel}</span>
                                    </div>
                                  )}
                                  {channel.type === 'webhook' && channel.config?.url && (
                                    <div className="flex items-center gap-2">
                                      <span className="material-icons text-sm">link</span>
                                      <span className="truncate">URL: {channel.config.url}</span>
                                    </div>
                                  )}
                                  {channel.type === 'teams' && (
                                    <div className="flex items-center gap-2">
                                      <span className="material-icons text-sm">groups</span>
                                      <span>Microsoft Teams</span>
                                    </div>
                                  )}
                                  {channel.type === 'pagerduty' && (
                                    <div className="flex items-center gap-2">
                                      <span className="material-icons text-sm">notification_important</span>
                                      <span>PagerDuty Integration</span>
                                    </div>
                                  )}
                                  {channel.type === 'opsgenie' && (
                                    <div className="flex items-center gap-2">
                                      <span className="material-icons text-sm">support</span>
                                      <span>Opsgenie Integration</span>
                                    </div>
                                  )}
                                </div>
                              </div>

                              <div className="flex gap-1 ml-4">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleTestChannel(channel.id)}
                                  className="p-2"
                                  title="Test Channel"
                                >
                                  <span className="material-icons text-base">send</span>
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => {
                                    setEditingChannel(channel)
                                    setShowChannelEditor(true)
                                  }}
                                  className="p-2"
                                  title="Edit Channel"
                                >
                                  <span className="material-icons text-base">edit</span>
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleDeleteChannel(channel.id)}
                                  className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-900/20"
                                  title="Delete Channel"
                                >
                                  <span className="material-icons text-base">delete</span>
                                </Button>
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
                      <span className="material-icons text-5xl text-sre-text-muted mb-4 block">notifications_off</span>
                      <h3 className="text-xl font-semibold text-sre-text mb-2">No Channels Configured</h3>
                      <p className="text-sre-text-muted mb-6 max-w-md mx-auto">
                        Create notification channels to receive alerts via email, Slack, Teams, webhooks, and more.
                      </p>
                      <Button onClick={() => { setEditingChannel(null); setShowChannelEditor(true); }}>
                        <span className="material-icons text-sm mr-2">add</span>
                        Create Your First Channel
                      </Button>
                    </div>
                  )}
                </div>
            </>
          )}

          {activeTab === 'silences' && (
            <>
                <div className="space-y-6">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="material-icons text-2xl text-sre-primary">volume_off</span>
                      <div>
                        <h2 className="text-xl font-semibold text-sre-text">Active Silences</h2>
                        <p className="text-sm text-sre-text-muted">
                          {silences.length > 0
                            ? `${silences.length} silence${silences.length !== 1 ? 's' : ''} active`
                            : 'No active silences'
                          }
                        </p>
                      </div>
                    </div>
                    {silences.length > 0 && (
                      <Button onClick={() => setShowSilenceForm(true)}>
                        <span className="material-icons text-sm mr-2">add</span>
                        Create Silence
                      </Button>
                    )}
                  </div>

                  {silences.length > 0 ? (
                    <div className="space-y-4">
                      {silences.map((s) => {
                        const visibilityLabel = s.visibility === 'tenant'
                          ? 'Public'
                          : s.visibility === 'group'
                            ? 'Group'
                            : 'Private'

                        return (
                          <div
                            key={s.id}
                            className="p-6 bg-sre-surface border-2 border-sre-border rounded-xl hover:border-sre-primary/50 hover:shadow-md transition-all duration-200"
                          >
                            <div className="flex items-start justify-between">
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-3 mb-3">
                                  <div className="p-2 rounded-lg bg-orange-100 dark:bg-orange-900/30">
                                    <span className="material-icons text-xl text-orange-600 dark:text-orange-400">volume_off</span>
                                  </div>
                                  <div>
                                    <h3 className="font-semibold text-sre-text text-lg">Silence Active</h3>
                                    <div className="flex items-center gap-2 mt-1">
                                      <span className="px-2 py-1 rounded-full text-xs font-medium bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-200">
                                        Silenced
                                      </span>
                                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                                        s.visibility === 'tenant'
                                          ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200'
                                          : s.visibility === 'group'
                                          ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200'
                                          : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'
                                      }`}>
                                        {visibilityLabel}
                                      </span>
                                    </div>
                                  </div>
                                </div>

                                {s.comment && (
                                  <p className="text-sm text-sre-text-muted mb-3">{s.comment}</p>
                                )}

                                <div className="space-y-2 text-sm text-sre-text-muted">
                                  <div className="flex items-center gap-2">
                                    <span className="material-icons text-sm">fingerprint</span>
                                    <span className="font-mono text-xs">ID: {s.id.slice(0, 12)}...</span>
                                  </div>
                                  {s.matchers?.length > 0 && (
                                    <div className="flex items-start gap-2">
                                      <span className="material-icons text-sm mt-0.5">filter_list</span>
                                      <div className="flex flex-wrap gap-1">
                                        {s.matchers.map((m) => (
                                          <span
                                            key={`${m.name}-${m.isEqual ? 'eq' : 'neq'}-${m.value}`}
                                            className="text-xs px-2 py-1 bg-sre-bg-alt border border-sre-border rounded text-sre-text"
                                          >
                                            {m.name}{m.isEqual ? '=' : '!='}{m.value}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                  <div className="flex items-center gap-2">
                                    <span className="material-icons text-sm">schedule</span>
                                    <span>
                                      {new Date(s.starts_at || s.startsAt).toLocaleString()} → {new Date(s.ends_at || s.endsAt).toLocaleString()}
                                    </span>
                                  </div>
                                </div>
                              </div>

                              <div className="flex gap-1 ml-4">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleDeleteSilence(s.id)}
                                  className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-900/20"
                                  title="Delete Silence"
                                >
                                  <span className="material-icons text-base">delete</span>
                                </Button>
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
                      <span className="material-icons text-5xl text-sre-text-muted mb-4 block">volume_up</span>
                      <h3 className="text-xl font-semibold text-sre-text mb-2">No Active Silences</h3>
                      <p className="text-sre-text-muted mb-6 max-w-md mx-auto">
                        Silences temporarily suppress alert notifications. Create a silence to stop alerts during maintenance.
                      </p>
                      <Button onClick={() => setShowSilenceForm(true)}>
                        <span className="material-icons text-sm mr-2">add</span>
                        Create Silence
                      </Button>
                    </div>
                  )}
                </div>
            </>
          )}
        </>
      )}

      {/* Rule Editor Modal */}
      <Modal
        isOpen={showRuleEditor}
        onClose={() => { setShowRuleEditor(false); setEditingRule(null); }}
        title={editingRule ? 'Edit Alert Rule' : 'Create Alert Rule'}
        size="lg"
        closeOnOverlayClick={false}
      >
        <RuleEditor
          rule={editingRule}
          channels={channels}
          apiKeys={apiKeys}
          onSave={async (data) => {
            const ok = await handleSaveRule(data)
            if (ok) {
              setShowRuleEditor(false)
              setEditingRule(null)
            }
            return ok
          }}
          onCancel={() => { setShowRuleEditor(false); setEditingRule(null); }}
        />
      </Modal>

      {/* Channel Editor Modal */}
      <Modal
        isOpen={showChannelEditor}
        onClose={() => { setShowChannelEditor(false); setEditingChannel(null); }}
        title={editingChannel ? 'Edit Notification Channel' : 'Create Notification Channel'}
        size="lg"
        closeOnOverlayClick={false}
      >
        <ChannelEditor
          channel={editingChannel}
          onSave={(data) => { handleSaveChannel(data); setShowChannelEditor(false); setEditingChannel(null); }}
          onCancel={() => { setShowChannelEditor(false); setEditingChannel(null); }}
        />
      </Modal>

      {/* Silence Form Modal */}
      <Modal
        isOpen={showSilenceForm}
        onClose={() => setShowSilenceForm(false)}
        title="Create Silence"
        size="md"
        closeOnOverlayClick={false}
      >
        <SilenceForm
          onSave={(data) => { handleCreateSilence(data); setShowSilenceForm(false); }}
          onCancel={() => setShowSilenceForm(false)}
        />
      </Modal>

      <ConfirmModal
        isOpen={testDialog.isOpen}
        title={testDialog.title}
        message={testDialog.message}
        onConfirm={() => setTestDialog({ isOpen: false, title: '', message: '' })}
        onCancel={() => setTestDialog({ isOpen: false, title: '', message: '' })}
        confirmText="OK"
        variant="primary"
      />

      <ConfirmModal
        isOpen={confirmDialog.isOpen}
        title={confirmDialog.title}
        message={confirmDialog.message}
        onConfirm={confirmDialog.onConfirm}
        onCancel={() => setConfirmDialog(EMPTY_CONFIRM)}
        confirmText={confirmDialog.confirmText}
        variant={confirmDialog.variant}
      />
    </div>
  )
}
