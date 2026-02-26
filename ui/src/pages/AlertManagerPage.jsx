import { useState, useEffect, useMemo } from 'react'
import { createSilence, deleteSilence, createAlertRule, updateAlertRule, deleteAlertRule, testAlertRule, importAlertRules} from '../api'
import { Card, Button, Select, Alert, Spinner, Modal } from '../components/ui'
import { useToast } from '../contexts/ToastContext'
import ConfirmModal from '../components/ConfirmModal'
import HelpTooltip from '../components/HelpTooltip'
import RuleEditor from '../components/alertmanager/RuleEditor'
import SilenceForm from '../components/alertmanager/SilenceForm'
import { ALERT_SEVERITY_OPTIONS } from '../utils/constants'
import { useAuth } from '../contexts/AuthContext'
import { useLocalStorage, useAlertManagerData } from '../hooks'
import { EMPTY_CONFIRM_DIALOG, DEFAULT_ALERTMANAGER_METRIC_KEYS } from '../utils/alertmanagerChannelUtils'
import {
  shouldIgnoreAlertManagerError,
  buildRulePayload,
} from '../utils/alertmanagerRuleUtils'

export default function AlertManagerPage() {
  const { user } = useAuth()
  const apiKeys = useMemo(() => user?.api_keys || [], [user?.api_keys])
  const [activeTab, setActiveTab] = useLocalStorage('alertmanager-active-tab', 'alerts')
  const [showRuleEditor, setShowRuleEditor] = useState(false)
  const [showSilenceForm, setShowSilenceForm] = useState(false)
  const [editingRule, setEditingRule] = useState(null)
  const [filterSeverity, setFilterSeverity] = useLocalStorage('alertmanager-filter-severity', 'all')
  const [confirmDialog, setConfirmDialog] = useState(EMPTY_CONFIRM_DIALOG)

  const [testDialog, setTestDialog] = useState({ isOpen: false, title: '', message: '' })

  const [metricOrder, setMetricOrder] = useLocalStorage('alertmanager-metric-order', DEFAULT_ALERTMANAGER_METRIC_KEYS)
  const [showImportRulesModal, setShowImportRulesModal] = useState(false)
  const [importYamlContent, setImportYamlContent] = useState('')
  const [importRunning, setImportRunning] = useState(false)
  const [importResult, setImportResult] = useState(null)
  const [importFileName, setImportFileName] = useState('')
  const { toast } = useToast()

  const { alerts, silences, rules, channels, loading, error, reloadData, setError: setHookError } = useAlertManagerData()

  useEffect(() => {
    const defaults = DEFAULT_ALERTMANAGER_METRIC_KEYS
    if (!Array.isArray(metricOrder)) {
      setMetricOrder(defaults)
      return
    }
    const missing = defaults.filter(k => !metricOrder.includes(k))
    if (missing.length > 0) {
      setMetricOrder([...metricOrder, ...missing])
    }
  }, [metricOrder, setMetricOrder])

  function handleApiError(e) {
    if (shouldIgnoreAlertManagerError(e)) return
    // delegate to hook-managed error state
    setHookError(e.message || String(e))
  }

  useEffect(() => {
    // initial load handled by hook; keep API compatibility for existing code paths
    // reloadData can be used after create/update/delete operations
  }, [reloadData])

  async function handleSaveRule(ruleData) {
    const payload = buildRulePayload(ruleData)

    try {
      if (editingRule) {
        await updateAlertRule(editingRule.id, payload)
      } else {
        await createAlertRule(payload)
      }
      await reloadData()
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
          await reloadData()
          setConfirmDialog(EMPTY_CONFIRM_DIALOG)
        } catch (e) {
          handleApiError(e)
          setConfirmDialog(EMPTY_CONFIRM_DIALOG)
        }
      }
    })
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
      await reloadData()
      setShowSilenceForm(false)
    } catch (e) {
      handleApiError(e)
    }
  }

  async function handleImportRules({ dryRun }) {
    setImportRunning(true)
    try {
      const result = await importAlertRules({
        yamlContent: importYamlContent,
        dryRun,
      })
      setImportResult(result)
      if (!dryRun) {
        await reloadData()
      }
    } catch (e) {
      handleApiError(e)
    } finally {
      setImportRunning(false)
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
          await reloadData()
          setConfirmDialog(EMPTY_CONFIRM_DIALOG)
        } catch (e) {
          handleApiError(e)
          setConfirmDialog(EMPTY_CONFIRM_DIALOG)
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
    totalChannels: channels.length,
  }), [alerts, silences, rules, channels])

  function getMetricData(key) {
    switch (key) {
      case 'activeAlerts':
        return {
          label: 'Active Alerts',
          value: stats.totalAlerts,
          detail: <><span className="text-red-500 dark:text-red-400">{stats.critical} critical</span> · <span className="text-yellow-500 dark:text-yellow-400">{stats.warning} warning</span></>
        }
      case 'alertRules':
        return { label: 'Alert Rules', value: `${stats.enabledRules}/${stats.totalRules}`, detail: 'enabled' }
      case 'channels':
        return { label: 'Notification Channels', value: `${stats.enabledChannels}/${stats.totalChannels}`, detail: 'active' }
      case 'silences':
        return { label: 'Active Silences', value: stats.activeSilences, detail: 'muting alerts' }
      default:
        return { label: key, value: '-', detail: '' }
    }
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-sre-text mb-2 flex items-center gap-2">
          <span className="material-icons text-3xl text-sre-primary">notifications_active</span>{' '}
          Be Notified
        </h1>
        <p className="text-sre-text-muted">Comprehensive alerting system with rules, channels, and silences</p>
      </div>

      {error && (
        <Alert variant="danger" className="mb-4">
          {error.split('\n').map((msg, idx) => (
            <div key={`err-${idx}`}>{msg}</div>
          ))}
        </Alert>
      )}

      {/* Draggable Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {metricOrder.map((key) => {
          const metricData = getMetricData(key)

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
          { key: 'silences', label: 'Silences', icon: 'volume_off' }
        ].map(tab => (
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
                    <div className="flex items-center gap-2">
                      <span className="material-icons text-xl text-sre-primary">warning</span>
                      <div>
                        <h2 className="text-lg font-semibold text-sre-text">Active Alerts</h2>
                        <p className="text-xs text-sre-text-muted">
                          {filteredAlerts.length > 0
                            ? `You've got ${filteredAlerts.length} alert${filteredAlerts.length !== 1 ? 's' : ''} firing`
                            : 'No active alerts'
                          }
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Select className="text-xs px-3 py-1" value={filterSeverity} onChange={(e) => setFilterSeverity(e.target.value)}>
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
                    <div className="flex items-center gap-2">
                      <Button
                        variant="secondary"
                        onClick={() => {
                          setImportResult(null)
                          setShowImportRulesModal(true)
                        }}
                      >
                        <span className="material-icons text-sm mr-2">upload_file</span>
                        Import YAML
                      </Button>
                      {rules.length > 0 && (
                        <Button onClick={() => { setEditingRule(null); setShowRuleEditor(true); }}>
                          <span className="material-icons text-sm mr-2">add</span>
                          Create Rule
                        </Button>
                      )}
                    </div>
                  </div>

                  {rules.length > 0 ? (
                    <div className="grid gap-4">
                      {rules.map((rule) => {
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

                                <div className="space-y-2 text-sm text-sre-text-muted p-4">
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
                                    <h3 className="font-semibold text-sre-text text-lg">{s.comment || 'Unnamed Silence'}</h3>
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
        isOpen={showImportRulesModal}
        onClose={() => setShowImportRulesModal(false)}
        title="Import Alert Rules from YAML"
        size="lg"
        closeOnOverlayClick={false}
      >
        <div className="space-y-4">
          <p className="text-sm text-sre-text-muted text-left">
            Paste Prometheus rule YAML. You can add optional <span className="font-mono">beobservant</span> metadata per rule for visibility, product key (<span className="font-mono">orgId</span>), channels, and shared groups.
          </p>

          <div className="bg-sre-surface/30 rounded-xl p-4 border border-sre-border/50">
            <h4 className="text-sm font-semibold text-sre-text mb-1 flex items-center gap-1">
              <span className="leading-none">Quick Templates</span>
            </h4>
            <p className="text-xs text-sre-text-muted mb-2">
              Start from a known-good template, then tune the expression and thresholds for your environment.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {[
                {
                  name: 'Memory Usage',
                  yaml: `groups:\n  - name: core-services-memory\n    rules:\n      - alert: HighMemoryUsage\n        expr: |\n          (\n            node_memory_MemTotal_bytes\n            - node_memory_MemAvailable_bytes\n          )\n          / node_memory_MemTotal_bytes > 0.80\n        for: 5m\n        labels:\n          severity: warning\n          service: core\n          resource: memory\n        annotations:\n          summary: High memory usage detected\n          description: >\n            Memory usage has exceeded 80% for more than 5 minutes.\n            This may indicate memory leaks, pod overcommitment, or insufficient node sizing.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]\n\n      - alert: CriticalMemoryUsage\n        expr: |\n          (\n            node_memory_MemTotal_bytes\n            - node_memory_MemAvailable_bytes\n          )\n          / node_memory_MemTotal_bytes > 0.92\n        for: 3m\n        labels:\n          severity: critical\n          service: core\n          resource: memory\n        annotations:\n          summary: Critical memory pressure\n          description: >\n            Memory usage is above 92%. OOM events are likely.\n            Immediate investigation required.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]`
                },
                {
                  name: 'CPU Usage',
                  yaml: `groups:\n  - name: core-services-cpu\n    rules:\n      - alert: HighCPUUsage\n        expr: avg(rate(cpu_seconds_total[5m])) > 0.80\n        for: 5m\n        labels:\n          severity: warning\n          service: core\n          resource: cpu\n        annotations:\n          summary: High CPU usage detected\n          description: >\n            CPU usage has exceeded 80% for more than 5 minutes.\n            This may indicate performance issues or insufficient CPU resources.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]\n\n      - alert: CriticalCPUUsage\n        expr: avg(rate(cpu_seconds_total[5m])) > 0.95\n        for: 3m\n        labels:\n          severity: critical\n          service: core\n          resource: cpu\n        annotations:\n          summary: Critical CPU usage\n          description: >\n            CPU usage is above 95%. System may become unresponsive.\n            Immediate action required.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]`
                },
                {
                  name: 'Disk Space',
                  yaml: `groups:\n  - name: infrastructure-disk\n    rules:\n      - alert: LowDiskSpace\n        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.15\n        for: 10m\n        labels:\n          severity: warning\n          service: infrastructure\n          resource: disk\n        annotations:\n          summary: Low disk space\n          description: >\n            Disk space is below 15%. Consider cleaning up old files or expanding storage.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]\n\n      - alert: CriticalDiskSpace\n        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.05\n        for: 5m\n        labels:\n          severity: critical\n          service: infrastructure\n          resource: disk\n        annotations:\n          summary: Critical disk space\n          description: >\n            Disk space is below 5%. System may fail to write data.\n            Immediate cleanup or expansion required.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]`
                },
                {
                  name: 'Service Availability',
                  yaml: `groups:\n  - name: service-availability\n    rules:\n      - alert: ServiceDown\n        expr: up == 0\n        for: 2m\n        labels:\n          severity: critical\n          service: monitoring\n        annotations:\n          summary: Service is down\n          description: >\n            The service has been down for more than 2 minutes.\n            Check service logs and restart if necessary.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]\n\n      - alert: HighErrorRate\n        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05\n        for: 5m\n        labels:\n          severity: warning\n          service: api\n        annotations:\n          summary: High error rate\n          description: >\n            Error rate exceeds 5% for more than 5 minutes.\n            Investigate API issues or database connectivity.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]`
                }
              ].map((template) => (
                <button
                  key={template.name}
                  type="button"
                  onClick={() => {
                    setImportYamlContent(template.yaml)
                    setImportFileName(`${template.name} Template`)
                  }}
                  className="group flex items-center gap-3 p-3 rounded-lg border border-sre-border bg-sre-surface/50 hover:bg-sre-surface hover:border-sre-primary/30 transition-all duration-200 text-left"
                >
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-sre-primary/20 to-sre-primary/10 flex items-center justify-center flex-shrink-0">
                    <span className="material-icons text-sre-primary text-sm">
                      {template.name === 'Memory Usage' ? 'memory' :
                       template.name === 'CPU Usage' ? 'developer_board' :
                       template.name === 'Disk Space' ? 'storage' :
                       'dns'}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sre-text group-hover:text-sre-primary transition-colors">
                      {template.name}
                    </div>
                    <div className="text-xs text-sre-text-muted">
                      Pre-configured alert rules with beobservant metadata
                    </div>
                  </div>
                  <div className="flex-shrink-0">
                    <span className="material-icons text-sre-text-muted text-sm group-hover:text-sre-primary transition-colors">
                      chevron_right
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3 mb-2">

            <label className="inline-flex items-center gap-2 text-sm cursor-pointer text-sre-primary hover:underline">
              <input
                type="file"
                accept=".yaml,.yml,text/yaml"
                className="hidden"
                onChange={async (e) => {
                  const f = e.target.files && e.target.files[0]
                  if (!f) return
                  try {
                    const txt = await f.text()
                    setImportYamlContent(txt)
                    setImportFileName(f.name || 'uploaded.yaml')
                    toast && toast.success && toast.success('YAML loaded')
                  } catch (err) {
                    toast && toast.error && toast.error('Failed to read file')
                  }
                }}
              />
              <span className="material-icons text-sm">file_upload</span>
              Upload YAML
            </label>

            {importFileName && <div className="text-xs text-sre-text-muted ml-2">{importFileName}</div>}
          </div>

          <textarea
            value={importYamlContent}
            onChange={(e) => { setImportYamlContent(e.target.value); setImportFileName('') }}
            rows={14}
            className="w-full rounded border border-sre-border bg-sre-bg p-3 font-mono text-xs text-sre-text"
            placeholder={`groups:\n  - name: core-services-memory\n    rules:\n      - alert: HighMemoryUsage\n        expr: |\n          (\n            node_memory_MemTotal_bytes\n            - node_memory_MemAvailable_bytes\n          )\n          / node_memory_MemTotal_bytes > 0.80\n        for: 5m\n        labels:\n          severity: warning\n          service: core\n          resource: memory\n        annotations:\n          summary: High memory usage detected\n          description: >\n            Memory usage has exceeded 80% for more than 5 minutes.\n            This may indicate memory leaks, pod overcommitment, or insufficient node sizing.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]\n\n      - alert: CriticalMemoryUsage\n        expr: |\n          (\n            node_memory_MemTotal_bytes\n            - node_memory_MemAvailable_bytes\n          )\n          / node_memory_MemTotal_bytes > 0.92\n        for: 3m\n        labels:\n          severity: critical\n          service: core\n          resource: memory\n        annotations:\n          summary: Critical memory pressure\n          description: >\n            Memory usage is above 92%. OOM events are likely.\n            Immediate investigation required.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]`}
          />

          {importResult && (
            <Card className="p-3">
              <div className="text-sm text-sre-text">
                {importResult.status === 'preview'
                  ? `Preview parsed ${importResult.count || 0} rule(s).`
                  : `Imported ${importResult.count || 0} rule(s) (${importResult.created || 0} created, ${importResult.updated || 0} updated).`}
              </div>
            </Card>
          )}

          <div className="flex items-center justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowImportRulesModal(false)}>
              Close
            </Button>
            <Button
              variant="secondary"
              disabled={importRunning || !importYamlContent.trim()}
              onClick={() => handleImportRules({ dryRun: true })}
            >
              {importRunning ? 'Working…' : 'Preview'}
            </Button>
            <Button
              disabled={importRunning || !importYamlContent.trim()}
              onClick={() => handleImportRules({ dryRun: false })}
            >
              {importRunning ? 'Importing…' : 'Import'}
            </Button>
          </div>
        </div>
      </Modal>

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

      {testDialog.isOpen && (
        <ConfirmModal
          isOpen={testDialog.isOpen}
          title={testDialog.title}
          message={testDialog.message}
          onConfirm={() => setTestDialog({ isOpen: false, title: '', message: '' })}
          onCancel={() => setTestDialog({ isOpen: false, title: '', message: '' })}
          confirmText="OK"
          variant="primary"
        />
      )}

      {confirmDialog.isOpen && (
        <ConfirmModal
          isOpen={confirmDialog.isOpen}
          title={confirmDialog.title}
          message={confirmDialog.message}
          onConfirm={confirmDialog.onConfirm || (() => {})}
          onCancel={() => setConfirmDialog(EMPTY_CONFIRM_DIALOG)}
          confirmText={confirmDialog.confirmText}
          variant={confirmDialog.variant}
        />
      )}
    </div>
  )
}
