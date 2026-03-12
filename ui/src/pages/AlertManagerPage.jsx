import { useState, useEffect, useMemo, useRef } from "react";
import {
  createSilence,
  deleteSilence,
  createAlertRule,
  updateAlertRule,
  deleteAlertRule,
  testAlertRule,
  importAlertRules,
  setAlertRuleHidden,
  setSilenceHidden,
} from "../api";
import { Card, Button, Select, Spinner, Modal } from "../components/ui";
import { useToast } from "../contexts/ToastContext";
import ConfirmModal from "../components/ConfirmModal";
import HelpTooltip from "../components/HelpTooltip";
import RuleEditor from "../components/alertmanager/RuleEditor";
import SilenceForm from "../components/alertmanager/SilenceForm";
import { ALERT_SEVERITY_OPTIONS } from "../utils/constants";
import { useAuth } from "../contexts/AuthContext";
import { useLocalStorage, useAlertManagerData } from "../hooks";
import {
  EMPTY_CONFIRM_DIALOG,
  DEFAULT_ALERTMANAGER_METRIC_KEYS,
} from "../utils/alertmanagerChannelUtils";
import {
  buildRulePayload,
} from "../utils/alertmanagerRuleUtils";

export default function AlertManagerPage() {
  const { user } = useAuth();
  const apiKeys = useMemo(() => user?.api_keys || [], [user?.api_keys]);
  const apiKeyNameByScope = useMemo(() => {
    const out = new Map();
    for (const key of apiKeys) {
      const scope = String(key?.key || "").trim();
      const name = String(key?.name || "").trim();
      if (!scope || !name) continue;
      out.set(scope, name);
    }
    return out;
  }, [apiKeys]);
  const [activeTab, setActiveTab] = useLocalStorage(
    "alertmanager-active-tab",
    "alerts",
  );
  const [showRuleEditor, setShowRuleEditor] = useState(false);
  const [showSilenceForm, setShowSilenceForm] = useState(false);
  const [editingRule, setEditingRule] = useState(null);
  const [filterSeverity, setFilterSeverity] = useState("all");
  const [filterCorrelationId, setFilterCorrelationId] = useState("all");
  const [filterLabel, setFilterLabel] = useState("");
  const [appliedAlertFilters, setAppliedAlertFilters] = useState({
    severity: "all",
    correlationId: "all",
    label: "",
  });
  const [rulesOwnerFilter, setRulesOwnerFilter] = useState("all");
  const [rulesCorrelationSearch, setRulesCorrelationSearch] = useState("");
  const [rulesStatusFilter, setRulesStatusFilter] = useState("all");
  const [rulesSeverityFilter, setRulesSeverityFilter] = useState("all");
  const [rulesApiKeyFilter, setRulesApiKeyFilter] = useState("all");
  const [appliedRulesFilters, setAppliedRulesFilters] = useState({
    owner: "all",
    status: "all",
    severity: "all",
    orgId: "all",
    correlationId: "",
  });
  const [alertsFiltersExpanded, setAlertsFiltersExpanded] = useState(false);
  const [rulesFiltersExpanded, setRulesFiltersExpanded] = useState(false);
  const [confirmDialog, setConfirmDialog] = useState(EMPTY_CONFIRM_DIALOG);

  const [testDialog, setTestDialog] = useState({
    isOpen: false,
    title: "",
    message: "",
  });

  const [metricOrder, setMetricOrder] = useLocalStorage(
    "alertmanager-metric-order",
    DEFAULT_ALERTMANAGER_METRIC_KEYS,
  );
  const [showImportRulesModal, setShowImportRulesModal] = useState(false);
  const [showHiddenRules, setShowHiddenRules] = useLocalStorage(
    "alertmanager-show-hidden-rules",
    false,
  );
  const [showHiddenSilences, setShowHiddenSilences] = useLocalStorage(
    "alertmanager-show-hidden-silences",
    false,
  );
  const [importYamlContent, setImportYamlContent] = useState("");
  const [importRunning, setImportRunning] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importFileName, setImportFileName] = useState("");
  const toast = useToast();
  const lastErrorToastRef = useRef({ key: "", ts: 0 });

  const {
    alerts,
    silences,
    rules,
    channels,
    loading,
    reloadData,
    setError: setHookError,
  } = useAlertManagerData({
    showHiddenRules,
    showHiddenSilences,
    alertFilters: appliedAlertFilters,
    ruleFilters: appliedRulesFilters,
  });

  useEffect(() => {
    const defaults = DEFAULT_ALERTMANAGER_METRIC_KEYS;
    if (!Array.isArray(metricOrder)) {
      setMetricOrder(defaults);
      return;
    }
    const missing = defaults.filter((k) => !metricOrder.includes(k));
    if (missing.length > 0) {
      setMetricOrder([...metricOrder, ...missing]);
    }
  }, [metricOrder, setMetricOrder]);

  function handleApiError(e) {
    const msg =
      e?.body?.detail ||
      e?.body?.message ||
      e?.message ||
      String(e || "Request failed");
    const isPermissionDenied =
      Number(e?.status) === 403 ||
      String(msg).toLowerCase().includes("you do not have permission");
    if (!isPermissionDenied) {
      setHookError(msg);
    }
    const key = `${e?.status || "x"}:${msg}`;
    const now = Date.now();
    if (
      lastErrorToastRef.current.key === key &&
      now - lastErrorToastRef.current.ts < 2000
    ) {
      return;
    }
    lastErrorToastRef.current = { key, ts: now };
    toast.error(msg);
  }

  useEffect(() => {
    // Load data on mount and whenever reloadData changes (e.g. after actions)
  }, [reloadData]);

  async function handleSaveRule(ruleData) {
    const normalizedOrgIds = Array.from(
      new Set(
        (Array.isArray(ruleData?.orgIds) ? ruleData.orgIds : [])
          .map((value) => String(value || "").trim())
          .filter(Boolean),
      ),
    );

    const payloadWithProductName = (rawPayload, orgIdValue) => {
      const payload = { ...rawPayload };
      const annotations = { ...(payload.annotations || {}) };
      const normalizedOrg = String(orgIdValue || "").trim();
      const productName =
        (normalizedOrg && apiKeyNameByScope.get(normalizedOrg)) ||
        (normalizedOrg ? "" : String(apiKeys.find((k) => k?.is_default)?.name || "").trim());
      if (productName) {
        annotations.beobservantProductName = productName;
      }
      payload.annotations = annotations;
      return payload;
    };

    try {
      if (editingRule) {
        const targetOrgIds = normalizedOrgIds.length
          ? normalizedOrgIds
          : [String(ruleData?.orgId || "").trim()].filter(Boolean);
        const primaryOrgId = targetOrgIds[0] || ruleData?.orgId;
        const payload = payloadWithProductName(
          buildRulePayload({
            ...ruleData,
            orgId: primaryOrgId,
          }),
          primaryOrgId,
        );
        await updateAlertRule(editingRule.id, payload);
        if (targetOrgIds.length > 1) {
          for (const extraOrgId of targetOrgIds.slice(1)) {
            const extraPayload = payloadWithProductName(
              buildRulePayload({ ...ruleData, orgId: extraOrgId }),
              extraOrgId,
            );
            await createAlertRule(extraPayload);
          }
        }
      } else {
        if (normalizedOrgIds.length > 1) {
          for (const orgId of normalizedOrgIds) {
            const payload = payloadWithProductName(
              buildRulePayload({ ...ruleData, orgId }),
              orgId,
            );
            await createAlertRule(payload);
          }
        } else {
          const payload = payloadWithProductName(
            buildRulePayload(ruleData),
            ruleData?.orgId,
          );
          await createAlertRule(payload);
        }
      }
      await reloadData();
      return true;
    } catch (e) {
      handleApiError(e);
      return false;
    }
  }

  async function handleDeleteRule(ruleId) {
    setConfirmDialog({
      isOpen: true,
      title: "Delete Alert Rule",
      message:
        "Are you sure you want to delete this rule? This action cannot be undone.",
      confirmText: "Delete",
      variant: "danger",
      onConfirm: async () => {
        try {
          await deleteAlertRule(ruleId);
          await reloadData();
          setConfirmDialog(EMPTY_CONFIRM_DIALOG);
        } catch (e) {
          handleApiError(e);
          setConfirmDialog(EMPTY_CONFIRM_DIALOG);
        }
      },
    });
  }

  async function handleTestRule(ruleId) {
    try {
      const result = await testAlertRule(ruleId);
      setTestDialog({
        isOpen: true,
        title: "Success",
        message:
          result.message ||
          "We have invoked a test alert, please check your alerting system.",
      });
    } catch (e) {
      handleApiError(e);
    }
  }

  async function handleCreateSilence(silenceData) {
    try {
      await createSilence(silenceData);
      await reloadData();
      setShowSilenceForm(false);
    } catch (e) {
      handleApiError(e);
    }
  }

  async function handleImportRules({ dryRun }) {
    setImportRunning(true);
    try {
      const result = await importAlertRules({
        yamlContent: importYamlContent,
        dryRun,
      });
      setImportResult(result);
      if (!dryRun) {
        await reloadData();
      }
    } catch (e) {
      handleApiError(e);
    } finally {
      setImportRunning(false);
    }
  }

  async function handleDeleteSilence(silenceId) {
    setConfirmDialog({
      isOpen: true,
      title: "Delete Silence",
      message: "Are you sure you want to delete this silence?",
      confirmText: "Delete",
      variant: "danger",
      onConfirm: async () => {
        try {
          await deleteSilence(silenceId);
          await reloadData();
          setConfirmDialog(EMPTY_CONFIRM_DIALOG);
        } catch (e) {
          handleApiError(e);
          setConfirmDialog(EMPTY_CONFIRM_DIALOG);
        }
      },
    });
  }

  async function handleToggleRuleHidden(rule, hidden) {
    if (!rule?.id) return;
    if (hidden) {
      setConfirmDialog({
        isOpen: true,
        title: "Hide Alert Rule",
        message:
          'If you hide this shared alert rule, you will not receive alerts fired by it. This is only hidden for your account. Continue?',
        confirmText: "Hide Rule",
        variant: "danger",
        onConfirm: async () => {
          try {
            await setAlertRuleHidden(rule.id, true);
            await reloadData();
            setConfirmDialog(EMPTY_CONFIRM_DIALOG);
          } catch (e) {
            handleApiError(e);
            setConfirmDialog(EMPTY_CONFIRM_DIALOG);
          }
        },
      });
      return;
    }

    try {
      await setAlertRuleHidden(rule.id, false);
      await reloadData();
    } catch (e) {
      handleApiError(e);
    }
  }

  async function handleToggleSilenceHidden(silence, hidden) {
    const silenceId = silence?.id;
    if (!silenceId) return;
    if (hidden) {
      setConfirmDialog({
        isOpen: true,
        title: "Hide Silence",
        message:
          'If you hide this shared silence, you will not see it in your active silences list unless "Show hidden" is enabled. This is only hidden for your account. Continue?',
        confirmText: "Hide Silence",
        variant: "danger",
        onConfirm: async () => {
          try {
            await setSilenceHidden(silenceId, true);
            await reloadData();
            setConfirmDialog(EMPTY_CONFIRM_DIALOG);
          } catch (e) {
            handleApiError(e);
            setConfirmDialog(EMPTY_CONFIRM_DIALOG);
          }
        },
      });
      return;
    }

    try {
      await setSilenceHidden(silenceId, false);
      await reloadData();
    } catch (e) {
      handleApiError(e);
    }
  }

  const alertNameToCorrelationId = useMemo(() => {
    const mapping = {};
    for (const rule of rules || []) {
      const ruleName = String(rule?.name || "").trim();
      const correlationId = String(rule?.group || "").trim();
      if (!ruleName || !correlationId || mapping[ruleName]) continue;
      mapping[ruleName] = correlationId;
    }
    return mapping;
  }, [rules]);

  const correlationIdOptions = useMemo(() => {
    const values = new Set();
    for (const rule of rules || []) {
      const value = String(rule?.group || "").trim();
      if (value) values.add(value);
    }
    return Array.from(values).sort((a, b) => a.localeCompare(b));
  }, [rules]);

  const filteredAlerts = useMemo(() => {
    let filtered = alerts;
    if (filterSeverity !== "all") {
      filtered = filtered.filter((a) => a.labels?.severity === filterSeverity);
    }
    if (filterCorrelationId !== "all") {
      filtered = filtered.filter((a) => {
        const labels = a.labels || {};
        const alertName = String(labels.alertname || "").trim();
        const correlationId =
          alertNameToCorrelationId[alertName] ||
          String(
            labels.correlation_id ||
              labels.correlationId ||
              labels.group ||
              labels.alertgroup ||
              "",
          ).trim();
        return correlationId === filterCorrelationId;
      });
    }
    const rawLabelFilter = String(filterLabel || "").trim();
    if (rawLabelFilter) {
      const normalized = rawLabelFilter.toLowerCase();
      const eqIndex = normalized.indexOf("=");
      if (eqIndex > 0) {
        const keyPart = normalized.slice(0, eqIndex).trim();
        const valuePart = normalized.slice(eqIndex + 1).trim();
        filtered = filtered.filter((a) => {
          const labels = a.labels || {};
          const candidate = String(labels[keyPart] ?? "").toLowerCase();
          return candidate.includes(valuePart);
        });
      } else {
        filtered = filtered.filter((a) => {
          const labels = a.labels || {};
          return Object.entries(labels).some(
            ([k, v]) =>
              String(k || "").toLowerCase().includes(normalized) ||
              String(v || "").toLowerCase().includes(normalized),
          );
        });
      }
    }
    return filtered;
  }, [
    alerts,
    filterSeverity,
    filterCorrelationId,
    filterLabel,
    alertNameToCorrelationId,
  ]);

  const ruleApiKeyOptions = useMemo(() => {
    const options = new Map();
    for (const key of apiKeys || []) {
      const scope = String(key?.key || "").trim();
      if (!scope) continue;
      const label = String(key?.name || "").trim() || `${scope.slice(0, 8)}...`;
      options.set(scope, label);
    }
    for (const rule of rules || []) {
      const scope = String(rule?.orgId || rule?.org_id || "").trim();
      if (!scope || options.has(scope)) continue;
      options.set(scope, `${scope.slice(0, 8)}...`);
    }
    return Array.from(options.entries())
      .sort((a, b) => a[1].localeCompare(b[1]))
      .map(([value, label]) => ({ value, label }));
  }, [apiKeys, rules]);

  const filteredRules = useMemo(() => {
    const currentUserId = String(user?.id || "").trim();
    const correlationQuery = String(rulesCorrelationSearch || "").trim().toLowerCase();

    return (rules || []).filter((rule) => {
      const ownerId = String(rule?.createdBy || rule?.created_by || "").trim();
      const isOwnRule = Boolean(currentUserId && ownerId && ownerId === currentUserId);
      const correlationId = String(rule?.group || "").trim();
      const severity = String(rule?.severity || "").toLowerCase();
      const enabled = Boolean(rule?.enabled);
      const orgScope = String(rule?.orgId || rule?.org_id || "").trim();

      if (rulesOwnerFilter === "owned" && !isOwnRule) return false;
      if (rulesOwnerFilter === "shared" && isOwnRule) return false;
      if (rulesStatusFilter === "enabled" && !enabled) return false;
      if (rulesStatusFilter === "disabled" && enabled) return false;
      if (rulesSeverityFilter !== "all" && severity !== rulesSeverityFilter) return false;
      if (rulesApiKeyFilter === "__all_products__" && orgScope) return false;
      if (
        rulesApiKeyFilter !== "all" &&
        rulesApiKeyFilter !== "__all_products__" &&
        orgScope !== rulesApiKeyFilter
      ) {
        return false;
      }
      if (correlationQuery && !correlationId.toLowerCase().includes(correlationQuery)) {
        return false;
      }
      return true;
    });
  }, [
    rules,
    user?.id,
    rulesOwnerFilter,
    rulesCorrelationSearch,
    rulesStatusFilter,
    rulesSeverityFilter,
    rulesApiKeyFilter,
  ]);

  const isRulesFilterActive =
    rulesOwnerFilter !== "all" ||
    rulesStatusFilter !== "all" ||
    rulesSeverityFilter !== "all" ||
    rulesApiKeyFilter !== "all" ||
    String(rulesCorrelationSearch || "").trim() !== "";
  const hasActiveAlertFilters =
    filterSeverity !== "all" ||
    filterCorrelationId !== "all" ||
    String(filterLabel || "").trim() !== "";

  const orgIdToName = useMemo(() => {
    const map = {};
    for (const k of apiKeys) {
      if (k.key) map[k.key] = k.name;
    }
    return map;
  }, [apiKeys]);

  const stats = useMemo(
    () => ({
      totalAlerts: alerts.length,
      critical: alerts.filter((a) => a.labels?.severity === "critical").length,
      warning: alerts.filter((a) => a.labels?.severity === "warning").length,
      activeSilences: silences.length,
      enabledRules: rules.filter((r) => r.enabled).length,
      totalRules: rules.length,
      enabledChannels: channels.filter((c) => c.enabled).length,
      totalChannels: channels.length,
    }),
    [alerts, silences, rules, channels],
  );

  function getMetricData(key) {
    switch (key) {
      case "activeAlerts":
        return {
          label: "Active Alerts",
          value: stats.totalAlerts,
          detail: (
            <>
              <span className="text-red-500 dark:text-red-400">
                {stats.critical} critical
              </span>{" "}
              ·{" "}
              <span className="text-yellow-500 dark:text-yellow-400">
                {stats.warning} warning
              </span>
            </>
          ),
        };
      case "alertRules":
        return {
          label: "Alert Rules",
          value: `${stats.enabledRules}/${stats.totalRules}`,
          detail: "enabled",
        };
      case "channels":
        return {
          label: "Notification Channels",
          value: `${stats.enabledChannels}/${stats.totalChannels}`,
          detail: "active",
        };
      case "silences":
        return {
          label: "Active Silences",
          value: stats.activeSilences,
          detail: "muting alerts",
        };
      default:
        return { label: key, value: "-", detail: "" };
    }
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-sre-text mb-2 flex items-center gap-2">
          <span className="material-icons text-3xl text-sre-primary">
            notifications_active
          </span>{" "}
          Alerts &amp; Rules
        </h1>
        <p className="text-sre-text-muted">
          Comprehensive alerting system with rules, channels, and silences
        </p>
      </div>

      {/* Draggable Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {metricOrder.map((key) => {
          const metricData = getMetricData(key);

          return (
            <div
              key={key}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.effectAllowed = "move";
                e.dataTransfer.setData("text/plain", key);
                e.currentTarget.classList.add("opacity-50", "scale-95");
              }}
              onDragOver={(e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
              }}
              onDrop={(e) => {
                e.preventDefault();
                try {
                  const sourceKey = e.dataTransfer.getData("text/plain");
                  if (!sourceKey || sourceKey === key) return;
                  const next = [...metricOrder];
                  const fromIdx = next.indexOf(sourceKey);
                  const toIdx = next.indexOf(key);
                  if (fromIdx === -1 || toIdx === -1) return;
                  next[fromIdx] = key;
                  next[toIdx] = sourceKey;
                  setMetricOrder(next);
                } catch {
                  /* ignore */
                }
              }}
              onDragEnd={(e) => {
                e.currentTarget.classList.remove("opacity-50", "scale-95");
              }}
              title="Drag to rearrange"
              className="cursor-move transition-transform duration-200 ease-out will-change-transform"
            >
              <Card className="p-4 relative overflow-visible bg-gradient-to-br from-sre-surface to-sre-surface/80 border-2 border-sre-border/50 hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm">
                <div className="absolute top-2 right-2 text-sre-text-muted hover:text-sre-text transition-colors">
                  <span
                    className="material-icons text-sm drag-handle"
                    aria-hidden
                  >
                    drag_indicator
                  </span>
                </div>
                <div className="text-sre-text-muted text-xs mb-1">
                  {metricData.label}
                </div>
                <div className="text-2xl font-bold text-sre-text">
                  {metricData.value}
                </div>
                <div className="text-xs text-sre-text-muted mt-1">
                  {metricData.detail}
                </div>
              </Card>
            </div>
          );
        })}
      </div>

      <div className="mb-6 flex gap-2 border-b border-sre-border justify-center items-center">
        {[
          { key: "alerts", label: "Alerts", icon: "notification_important" },
          { key: "rules", label: "Rules", icon: "rule" },
          { key: "silences", label: "Silences", icon: "volume_off" },
        ].map((tab) => (
          <button
            type="button"
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`pl-4 pr-4 py-2 text-sm flex items-center justify-center gap-2 border-b-2 transition-colors ${
              activeTab === tab.key
                ? "border-sre-primary text-sre-primary"
                : "border-transparent text-sre-text-muted hover:text-sre-text"
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
          {activeTab === "alerts" && (
            <>
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="material-icons text-xl text-sre-primary">
                      warning
                    </span>
                    <div>
                      <h2 className="text-lg font-semibold text-sre-text">
                        Active Alerts
                      </h2>
                      <p className="text-xs text-sre-text-muted">
                        {filteredAlerts.length > 0
                          ? `You've got ${filteredAlerts.length} alert${filteredAlerts.length !== 1 ? "s" : ""} firing`
                          : "No active alerts"}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="bg-gradient-to-r from-sre-surface to-sre-bg-alt rounded-xl border border-sre-border/50 shadow-sm overflow-hidden">
                  <div className="flex items-center justify-between p-4 hover:bg-sre-surface/50 transition-colors duration-200">
                    <button
                      type="button"
                      onClick={() => setAlertsFiltersExpanded((prev) => !prev)}
                      className="flex-1 flex items-center justify-between"
                    >
                      <div className="flex items-center gap-3">
                        <span className="material-icons text-sre-primary">
                          {alertsFiltersExpanded ? "expand_less" : "expand_more"}
                        </span>
                        <span className="text-sm font-semibold text-sre-text">Filters</span>
                        {hasActiveAlertFilters && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-sre-primary/15 text-sre-primary">
                            Active
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-sre-text-muted">
                        {hasActiveAlertFilters ? "Filters applied" : "Click to filter"}
                      </div>
                    </button>
                    <div className="ml-3">
                      <HelpTooltip text="Filter alerts by label, severity, or correlation ID. Label filter supports key=value or free text." />
                    </div>
                  </div>
                  {alertsFiltersExpanded && (
                    <div className="px-4 pb-4 border-t border-sre-border/30">
                      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end pt-4">
                        <div>
                          <label className="block text-xs text-sre-text-muted mb-1">Label</label>
                          <input
                            type="text"
                            value={filterLabel}
                            onChange={(e) => setFilterLabel(e.target.value)}
                            placeholder="instance=node-1"
                            className="w-full text-sm px-3 py-2 rounded border border-sre-border bg-sre-surface text-sre-text"
                          />
                        </div>
                        <div>
                          <label className="block text-xs text-sre-text-muted mb-1">Severity</label>
                          <Select
                            value={filterSeverity}
                            onChange={(e) => setFilterSeverity(e.target.value)}
                          >
                            {ALERT_SEVERITY_OPTIONS.map((opt) => (
                              <option key={opt.value} value={opt.value}>
                                {opt.label}
                              </option>
                            ))}
                          </Select>
                        </div>
                        <div>
                          <label className="block text-xs text-sre-text-muted mb-1">
                            Correlation ID
                          </label>
                          <Select
                            value={filterCorrelationId}
                            onChange={(e) => setFilterCorrelationId(e.target.value)}
                          >
                            <option value="all">All correlation IDs</option>
                            {correlationIdOptions.map((id) => (
                              <option key={id} value={id}>
                                {id}
                              </option>
                            ))}
                          </Select>
                        </div>
                        <div className="flex items-center justify-end gap-2">
                          {hasActiveAlertFilters && (
                            <Button
                              variant="secondary"
                              onClick={() => {
                                setFilterLabel("");
                                setFilterSeverity("all");
                                setFilterCorrelationId("all");
                                setAppliedAlertFilters({
                                  severity: "all",
                                  correlationId: "all",
                                  label: "",
                                });
                              }}
                            >
                              Clear
                            </Button>
                          )}
                          <Button
                            variant="primary"
                            onClick={() => {
                              setAppliedAlertFilters({
                                severity: filterSeverity,
                                correlationId: filterCorrelationId,
                                label: filterLabel,
                              });
                              setAlertsFiltersExpanded(false);
                            }}
                          >
                            Apply
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {filteredAlerts.length > 0 ? (
                  <div className="space-y-4">
                    {filteredAlerts.map((a, idx) => {
                      const labels = a.labels || {};
                      const alertName = String(labels.alertname || "").trim();
                      const correlationId =
                        alertNameToCorrelationId[alertName] ||
                        String(
                          labels.correlation_id ||
                            labels.correlationId ||
                            labels.group ||
                            labels.alertgroup ||
                            "",
                        ).trim();
                      return (
                        <div
                          key={a.fingerprint || a.id || a.starts_at || idx}
                          className="p-6 bg-sre-surface border-2 border-sre-border rounded-xl hover:border-sre-primary/50 hover:shadow-md transition-all duration-200"
                        >
                        <div className="flex items-start justify-between">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-3 mb-3">
                              <div
                                className={`p-2 rounded-lg ${
                                  a.labels?.severity === "critical"
                                    ? "bg-red-100 dark:bg-red-900/30"
                                    : "bg-yellow-100 dark:bg-yellow-900/30"
                                }`}
                              >
                                <span
                                  className={`material-icons text-xl ${
                                    a.labels?.severity === "critical"
                                      ? "text-red-600 dark:text-red-400"
                                      : "text-yellow-600 dark:text-yellow-400"
                                  }`}
                                >
                                  {a.labels?.severity === "critical"
                                    ? "error"
                                    : "warning"}
                                </span>
                              </div>
                              <div>
                                <h3 className="font-semibold text-sre-text text-lg">
                                  {a.labels?.alertname || "Unknown"}
                                </h3>
                                <div className="flex items-center gap-2 mt-1">
                                  <span
                                    className={`px-2 py-1 rounded-full text-xs font-medium ${
                                      a.labels?.severity === "critical"
                                        ? "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200"
                                        : "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-200"
                                    }`}
                                  >
                                    {a.labels?.severity || "unknown"}
                                  </span>
                                  <span
                                    className={`px-2 py-1 rounded-full text-xs font-medium ${
                                      a.status?.state === "active"
                                        ? "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200"
                                        : "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200"
                                    }`}
                                  >
                                    {a.status?.state || "active"}
                                  </span>
                                  {correlationId && (
                                    <span className="px-2 py-1 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-200">
                                      Correlation ID: {correlationId}
                                    </span>
                                  )}
                                </div>
                              </div>
                            </div>

                            {(a.annotations?.summary || (a.labels && Object.keys(a.labels).length > 0)) && (
                              <div className="flex flex-wrap items-center gap-2 mb-3">
                                {a.annotations?.summary && (
                                  <span className="text-sm text-sre-text-muted flex-1 min-w-0 truncate">
                                    {a.annotations.summary}
                                  </span>
                                )}

                                {a.labels && Object.keys(a.labels).length > 0 && (
                                  <div className="flex flex-wrap gap-2">
                                    {Object.entries(a.labels)
                                      .filter(
                                        ([key]) =>
                                          !["alertname", "severity"].includes(key),
                                      )
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
                            )}
                          </div>

                          <div className="flex flex-col items-end gap-2 ml-4">
                            <span className="text-xs text-sre-text-muted whitespace-nowrap">
                              {new Date(
                                a.starts_at || a.startsAt,
                              ).toLocaleString()}
                            </span>
                          </div>
                        </div>
                      </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
                    <span className="material-icons text-5xl text-sre-text-muted mb-4 block">
                      check_circle
                    </span>
                    <h3 className="text-xl font-semibold text-sre-text mb-2">
                      No Active Alerts
                    </h3>
                    <p className="text-sre-text-muted text-sm mb-6 max-w-md mx-auto">
                      All systems are running smoothly. No alerts are currently
                      firing.
                    </p>
                  </div>
                )}
              </div>
            </>
          )}

          {activeTab === "rules" && (
            <>
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="material-icons text-2xl text-sre-primary">
                      rule
                    </span>
                    <div>
                      <h2 className="text-xl font-semibold text-sre-text">
                        Alert Rules
                      </h2>
                      <p className="text-sm text-sre-text-muted">
                        {rules.length > 0
                          ? isRulesFilterActive
                            ? `Showing ${filteredRules.length} of ${rules.length} rule${rules.length !== 1 ? "s" : ""}`
                            : `${rules.length} rule${rules.length !== 1 ? "s" : ""} configured`
                          : "No rules configured"}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="inline-flex items-center gap-2 text-xs text-sre-text-muted">
                      <input
                        type="checkbox"
                        checked={!!showHiddenRules}
                        onChange={(e) => setShowHiddenRules(e.target.checked)}
                      />
                      Show hidden
                    </label>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setImportResult(null);
                        setShowImportRulesModal(true);
                      }}
                      size="sm"
                    >
                      <span className="material-icons text-sm mr-2">
                        upload_file
                      </span>
                      Import YAML
                    </Button>
                    {rules.length > 0 && (
                      <Button
                        onClick={() => {
                          setEditingRule(null);
                          setShowRuleEditor(true);
                        }}
                        size="sm"
                      >
                        <span className="material-icons text-sm mr-2">add</span>
                        Create Rule
                      </Button>
                    )}
                  </div>
                </div>

                {rules.length > 0 ? (
                  <>
                    <div className="bg-gradient-to-r from-sre-surface to-sre-bg-alt rounded-xl border border-sre-border/50 shadow-sm overflow-hidden">
                      <button
                        type="button"
                        onClick={() => setRulesFiltersExpanded((prev) => !prev)}
                        className="w-full flex items-center justify-between p-4 hover:bg-sre-surface/50 transition-colors duration-200"
                      >
                        <div className="flex items-center gap-3">
                          <span className="material-icons text-sre-primary">
                            {rulesFiltersExpanded ? "expand_less" : "expand_more"}
                          </span>
                          <span className="text-sm font-semibold text-sre-text">Filters</span>
                          {isRulesFilterActive && (
                            <span className="text-xs px-2 py-0.5 rounded-full bg-sre-primary/15 text-sre-primary">
                              Active
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-sre-text-muted">
                          {isRulesFilterActive ? "Filters applied" : "Click to filter"}
                        </div>
                      </button>
                      {rulesFiltersExpanded && (
                        <div className="px-4 pb-4 border-t border-sre-border/30">
                          <div className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end pt-4">
                            <div>
                              <label className="block text-xs text-sre-text-muted mb-1">Owner</label>
                              <Select
                                value={rulesOwnerFilter}
                                onChange={(e) => setRulesOwnerFilter(e.target.value)}
                              >
                                <option value="all">All</option>
                                <option value="owned">Owned</option>
                                <option value="shared">Shared</option>
                              </Select>
                            </div>
                            <div>
                              <label className="block text-xs text-sre-text-muted mb-1">Status</label>
                              <Select
                                value={rulesStatusFilter}
                                onChange={(e) => setRulesStatusFilter(e.target.value)}
                              >
                                <option value="all">All</option>
                                <option value="enabled">Enabled</option>
                                <option value="disabled">Disabled</option>
                              </Select>
                            </div>
                            <div>
                              <label className="block text-xs text-sre-text-muted mb-1">Severity</label>
                              <Select
                                value={rulesSeverityFilter}
                                onChange={(e) => setRulesSeverityFilter(e.target.value)}
                              >
                                <option value="all">All</option>
                                {ALERT_SEVERITY_OPTIONS.map((opt) => (
                                  <option key={opt.value} value={opt.value}>
                                    {opt.label}
                                  </option>
                                ))}
                              </Select>
                            </div>
                            <div>
                              <label className="block text-xs text-sre-text-muted mb-1">API Key</label>
                              <Select
                                value={rulesApiKeyFilter}
                                onChange={(e) => setRulesApiKeyFilter(e.target.value)}
                              >
                                <option value="all">All API keys</option>
                                <option value="__all_products__">All products</option>
                                {ruleApiKeyOptions.map((opt) => (
                                  <option key={opt.value} value={opt.value}>
                                    {opt.label}
                                  </option>
                                ))}
                              </Select>
                            </div>
                            <div>
                              <label className="block text-xs text-sre-text-muted mb-1">
                                Correlation ID
                              </label>
                              <input
                                type="text"
                                value={rulesCorrelationSearch}
                                onChange={(e) => setRulesCorrelationSearch(e.target.value)}
                                placeholder="Search correlation ID"
                                className="w-full px-3 py-2 bg-sre-surface border border-sre-border rounded-lg text-sre-text"
                              />
                            </div>
                          </div>
                          <div className="flex justify-end gap-2 pt-3">
                            {isRulesFilterActive && (
                              <Button
                                variant="secondary"
                                onClick={() => {
                                  setRulesOwnerFilter("all");
                                  setRulesStatusFilter("all");
                                  setRulesSeverityFilter("all");
                                  setRulesApiKeyFilter("all");
                                  setRulesCorrelationSearch("");
                                  setAppliedRulesFilters({
                                    owner: "all",
                                    status: "all",
                                    severity: "all",
                                    orgId: "all",
                                    correlationId: "",
                                  });
                                }}
                              >
                                Clear
                              </Button>
                            )}
                            <Button
                              variant="primary"
                              onClick={() => {
                                setAppliedRulesFilters({
                                  owner: rulesOwnerFilter,
                                  status: rulesStatusFilter,
                                  severity: rulesSeverityFilter,
                                  orgId: rulesApiKeyFilter,
                                  correlationId: rulesCorrelationSearch,
                                });
                                setRulesFiltersExpanded(false);
                              }}
                            >
                              Apply
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>

                    {filteredRules.length > 0 ? (
                      <div className="grid gap-4">
                        {filteredRules.map((rule) => {
                      const ownerId = String(rule.createdBy || rule.created_by || "");
                      const isOwnRule = ownerId && ownerId === String(user?.id || "");
                      const canHideRule = !isOwnRule;
                      return (
                        <div
                          key={rule.id}
                          className={`p-6 bg-sre-surface border-2 rounded-xl hover:border-sre-primary/50 hover:shadow-md transition-all duration-200 ${
                            rule.isHidden || rule.is_hidden
                              ? "border-amber-400/60 opacity-90"
                              : "border-sre-border"
                          }`}
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-3 mb-3">
                                <div
                                  className={`p-2 rounded-lg ${
                                    rule.severity === "critical"
                                      ? "bg-red-100 dark:bg-red-900/30"
                                      : rule.severity === "warning"
                                        ? "bg-yellow-100 dark:bg-yellow-900/30"
                                        : "bg-blue-100 dark:bg-blue-900/30"
                                  }`}
                                >
                                  <span
                                    className={`material-icons text-xl ${
                                      rule.severity === "critical"
                                        ? "text-red-600 dark:text-red-400"
                                        : rule.severity === "warning"
                                          ? "text-yellow-600 dark:text-yellow-400"
                                          : "text-blue-600 dark:text-blue-400"
                                    }`}
                                  >
                                    {rule.severity === "critical"
                                      ? "error"
                                      : rule.severity === "warning"
                                        ? "warning"
                                        : "info"}
                                  </span>
                                </div>
                                <div>
                                  <h3 className="font-semibold text-sre-text text-lg">
                                    {rule.name}
                                  </h3>
                                  <div className="flex items-center gap-2 mt-1">
                                    <span
                                      className={`px-2 py-1 rounded-full text-xs font-medium ${
                                        rule.severity === "critical"
                                          ? "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200"
                                          : rule.severity === "warning"
                                            ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-200"
                                            : "bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200"
                                      }`}
                                    >
                                      {rule.severity}
                                    </span>
                                    <span
                                      className={`px-2 py-1 rounded-full text-xs font-medium ${
                                        rule.enabled
                                          ? "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200"
                                          : "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200"
                                      }`}
                                    >
                                      {rule.enabled ? "Enabled" : "Disabled"}
                                    </span>
                                    <span className="px-2 py-1 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-200">
                                      Correlation ID: {rule.group}
                                    </span>
                                    {(rule.isHidden || rule.is_hidden) && (
                                      <span className="px-2 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200">
                                        Hidden
                                      </span>
                                    )}
                                    {rule.orgId ? (
                                      <span className="px-2 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-200">
                                        {orgIdToName[rule.orgId] ||
                                          `${rule.orgId.slice(0, 8)}...`}
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
                                  <span className="material-icons text-sm">
                                    functions
                                  </span>
                                  <span className="font-mono text-xs bg-sre-bg-alt px-2 py-1 rounded border">
                                    {rule.expr}
                                  </span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="material-icons text-sm">
                                    schedule
                                  </span>
                                  <span>Duration: {rule.duration}</span>
                                </div>
                                {rule.annotations?.summary && (
                                  <div className="flex items-start gap-2">
                                    <span className="material-icons text-sm mt-0.5">
                                      description
                                    </span>
                                    <span>{rule.annotations.summary}</span>
                                  </div>
                                )}
                              </div>
                            </div>

                            <div className="flex gap-1 ml-4">
                              {canHideRule && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() =>
                                    handleToggleRuleHidden(
                                      rule,
                                      !(rule.isHidden || rule.is_hidden),
                                    )
                                  }
                                  className="p-2"
                                  title={
                                    rule.isHidden || rule.is_hidden
                                      ? "Unhide Rule"
                                      : "Hide Rule"
                                  }
                                >
                                  <span className="material-icons text-base">
                                    {rule.isHidden || rule.is_hidden
                                      ? "visibility"
                                      : "visibility_off"}
                                  </span>
                                </Button>
                              )}
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleTestRule(rule.id)}
                                className="p-2"
                                title="Test Rule"
                              >
                                <span className="material-icons text-base">
                                  science
                                </span>
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  setEditingRule(rule);
                                  setShowRuleEditor(true);
                                }}
                                className="p-2"
                                title="Edit Rule"
                              >
                                <span className="material-icons text-base">
                                  edit
                                </span>
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDeleteRule(rule.id)}
                                className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-900/20"
                                title="Delete Rule"
                              >
                                <span className="material-icons text-base">
                                  delete
                                </span>
                              </Button>
                            </div>
                          </div>
                        </div>
                      );
                        })}
                      </div>
                    ) : (
                      <div className="text-center py-12 px-6 rounded-xl border border-sre-border bg-sre-bg-alt">
                        <h3 className="text-lg font-semibold text-sre-text mb-2">
                          No Rules Match Current Filters
                        </h3>
                        <p className="text-sre-text-muted text-sm">
                          Adjust your owner, status, severity, correlation ID, or API key filters.
                        </p>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
                    <span className="material-icons text-5xl text-sre-text-muted mb-4 block">
                      rule
                    </span>
                    <h3 className="text-xl font-semibold text-sre-text mb-2">
                      No Rules Configured
                    </h3>
                    <p className="text-sre-text-muted text-sm mb-6 max-w-md mx-auto">
                      Create alert rules to monitor your systems and get
                      notified when issues occur.
                    </p>
                    <Button
                      onClick={() => {
                        setEditingRule(null);
                        setShowRuleEditor(true);
                      }}
                    >
                      <span className="material-icons text-sm mr-2">add</span>
                      Create Your First Rule
                    </Button>
                  </div>
                )}
              </div>
            </>
          )}

          {activeTab === "silences" && (
            <>
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="material-icons text-2xl text-sre-primary">
                      volume_off
                    </span>
                    <div>
                      <h2 className="text-xl font-semibold text-sre-text">
                        Active Silences
                      </h2>
                      <p className="text-sm text-sre-text-muted">
                        {silences.length > 0
                          ? `${silences.length} silence${silences.length !== 1 ? "s" : ""} active`
                          : "No active silences"}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <label className="inline-flex items-center gap-2 text-xs text-sre-text-muted">
                      <input
                        type="checkbox"
                        checked={!!showHiddenSilences}
                        onChange={(e) =>
                          setShowHiddenSilences(e.target.checked)
                        }
                      />
                      Show hidden
                    </label>
                    {silences.length > 0 && (
                      <Button onClick={() => setShowSilenceForm(true)} size="sm">
                        <span className="material-icons text-sm mr-2">add</span>
                        Create Silence
                      </Button>
                    )}
                  </div>
                </div>

                {silences.length > 0 ? (
                  <div className="space-y-4">
                    {silences.map((s) => {
                      const silenceOwner = String(s.createdBy || s.created_by || "");
                      const isOwnSilence =
                        silenceOwner &&
                        silenceOwner === String(user?.id || "");
                      const canHideSilence = !isOwnSilence;
                      const visibilityLabel =
                        s.visibility === "tenant"
                          ? "Public"
                          : s.visibility === "group"
                            ? "Group"
                            : "Private";

                      return (
                        <div
                          key={s.id}
                          className={`p-6 bg-sre-surface border-2 rounded-xl hover:border-sre-primary/50 hover:shadow-md transition-all duration-200 ${
                            s.isHidden || s.is_hidden
                              ? "border-amber-400/60 opacity-90"
                              : "border-sre-border"
                          }`}
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-3 mb-3">
                                <div className="p-2 rounded-lg bg-orange-100 dark:bg-orange-900/30">
                                  <span className="material-icons text-xl text-orange-600 dark:text-orange-400">
                                    volume_off
                                  </span>
                                </div>
                                <div>
                                  <h3 className="font-semibold text-sre-text text-lg">
                                    {s.comment || "Unnamed Silence"}
                                  </h3>
                                  <div className="flex items-center gap-2 mt-1">
                                    <span className="px-2 py-1 rounded-full text-xs font-medium bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-200">
                                      Silenced
                                    </span>
                                    <span
                                      className={`px-2 py-1 rounded-full text-xs font-medium ${
                                        s.visibility === "tenant"
                                          ? "bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200"
                                          : s.visibility === "group"
                                            ? "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200"
                                            : "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200"
                                      }`}
                                    >
                                      {visibilityLabel}
                                    </span>
                                    {(s.isHidden || s.is_hidden) && (
                                      <span className="px-2 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200">
                                        Hidden
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>
                              <div className="space-y-2 text-sm text-sre-text-muted">
                                <div className="flex items-center gap-2">
                                  <span className="material-icons text-sm">
                                    fingerprint
                                  </span>
                                  <span className="font-mono text-xs">
                                    ID: {s.id.slice(0, 12)}...
                                  </span>
                                </div>
                                {s.matchers?.length > 0 && (
                                  <div className="flex items-start gap-2">
                                    <span className="material-icons text-sm mt-0.5">
                                      filter_list
                                    </span>
                                    <div className="flex flex-wrap gap-1">
                                      {s.matchers.map((m) => (
                                        <span
                                          key={`${m.name}-${m.isEqual ? "eq" : "neq"}-${m.value}`}
                                          className="text-xs px-2 py-1 bg-sre-bg-alt border border-sre-border rounded text-sre-text"
                                        >
                                          {m.name}
                                          {m.isEqual ? "=" : "!="}
                                          {m.value}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                <div className="flex items-center gap-2">
                                  <span className="material-icons text-sm">
                                    schedule
                                  </span>
                                  <span>
                                    {new Date(
                                      s.starts_at || s.startsAt,
                                    ).toLocaleString()}{" "}
                                    →{" "}
                                    {new Date(
                                      s.ends_at || s.endsAt,
                                    ).toLocaleString()}
                                  </span>
                                </div>
                              </div>
                            </div>

                            <div className="flex gap-1 ml-4">
                              {canHideSilence && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() =>
                                    handleToggleSilenceHidden(
                                      s,
                                      !(s.isHidden || s.is_hidden),
                                    )
                                  }
                                  className="p-2"
                                  title={
                                    s.isHidden || s.is_hidden
                                      ? "Unhide Silence"
                                      : "Hide Silence"
                                  }
                                >
                                  <span className="material-icons text-base">
                                    {s.isHidden || s.is_hidden
                                      ? "visibility"
                                      : "visibility_off"}
                                  </span>
                                </Button>
                              )}
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDeleteSilence(s.id)}
                                className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-900/20"
                                title="Delete Silence"
                              >
                                <span className="material-icons text-base">
                                  delete
                                </span>
                              </Button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
                    <span className="material-icons text-5xl text-sre-text-muted mb-4 block">
                      volume_up
                    </span>
                    <h3 className="text-xl font-semibold text-sre-text mb-2">
                      No Active Silences
                    </h3>
                    <p className="text-sre-text-muted text-sm mb-6 max-w-md mx-auto">
                      Silences temporarily suppress alert notifications. Create
                      a silence to stop alerts during maintenance.
                    </p>
                    <Button onClick={() => setShowSilenceForm(true)} size="sm">
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

      <Modal
        isOpen={showImportRulesModal}
        onClose={() => setShowImportRulesModal(false)}
        title="Import Alert Rules from YAML"
        size="lg"
        closeOnOverlayClick={false}
      >
        <div className="space-y-4">
          <p className="text-sm text-sre-text-muted text-left">
            Paste Prometheus rule YAML. You can add optional{" "}
            <span className="font-mono">beobservant</span> metadata per rule for
            visibility, product key (<span className="font-mono">orgId</span>),
            channels, and shared groups.
          </p>

          <div className="bg-sre-surface/30 rounded-xl p-4 border border-sre-border/50">
            <h4 className="text-sm font-semibold text-sre-text mb-1 flex items-center gap-1">
              <span className="leading-none">Quick Templates</span>
            </h4>
            <p className="text-xs text-sre-text-muted mb-2">
              Start from a known-good template, then tune the expression and
              thresholds for your environment.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {[
                {
                  name: "Memory Usage",
                  yaml: `groups:\n  - name: core-services-memory\n    rules:\n      - alert: HighMemoryUsage\n        expr: |\n          (\n            node_memory_MemTotal_bytes\n            - node_memory_MemAvailable_bytes\n          )\n          / node_memory_MemTotal_bytes > 0.80\n        for: 5m\n        labels:\n          severity: warning\n          service: core\n          resource: memory\n        annotations:\n          summary: High memory usage detected\n          description: >\n            Memory usage has exceeded 80% for more than 5 minutes.\n            This may indicate memory leaks, pod overcommitment, or insufficient node sizing.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]\n\n      - alert: CriticalMemoryUsage\n        expr: |\n          (\n            node_memory_MemTotal_bytes\n            - node_memory_MemAvailable_bytes\n          )\n          / node_memory_MemTotal_bytes > 0.92\n        for: 3m\n        labels:\n          severity: critical\n          service: core\n          resource: memory\n        annotations:\n          summary: Critical memory pressure\n          description: >\n            Memory usage is above 92%. OOM events are likely.\n            Immediate investigation required.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]`,
                },
                {
                  name: "CPU Usage",
                  yaml: `groups:\n  - name: core-services-cpu\n    rules:\n      - alert: HighCPUUsage\n        expr: avg(rate(cpu_seconds_total[5m])) > 0.80\n        for: 5m\n        labels:\n          severity: warning\n          service: core\n          resource: cpu\n        annotations:\n          summary: High CPU usage detected\n          description: >\n            CPU usage has exceeded 80% for more than 5 minutes.\n            This may indicate performance issues or insufficient CPU resources.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]\n\n      - alert: CriticalCPUUsage\n        expr: avg(rate(cpu_seconds_total[5m])) > 0.95\n        for: 3m\n        labels:\n          severity: critical\n          service: core\n          resource: cpu\n        annotations:\n          summary: Critical CPU usage\n          description: >\n            CPU usage is above 95%. System may become unresponsive.\n            Immediate action required.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]`,
                },
                {
                  name: "Disk Space",
                  yaml: `groups:\n  - name: infrastructure-disk\n    rules:\n      - alert: LowDiskSpace\n        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.15\n        for: 10m\n        labels:\n          severity: warning\n          service: infrastructure\n          resource: disk\n        annotations:\n          summary: Low disk space\n          description: >\n            Disk space is below 15%. Consider cleaning up old files or expanding storage.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]\n\n      - alert: CriticalDiskSpace\n        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.05\n        for: 5m\n        labels:\n          severity: critical\n          service: infrastructure\n          resource: disk\n        annotations:\n          summary: Critical disk space\n          description: >\n            Disk space is below 5%. System may fail to write data.\n            Immediate cleanup or expansion required.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]`,
                },
                {
                  name: "Service Availability",
                  yaml: `groups:\n  - name: service-availability\n    rules:\n      - alert: ServiceDown\n        expr: up == 0\n        for: 2m\n        labels:\n          severity: critical\n          service: monitoring\n        annotations:\n          summary: Service is down\n          description: >\n            The service has been down for more than 2 minutes.\n            Check service logs and restart if necessary.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]\n\n      - alert: HighErrorRate\n        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05\n        for: 5m\n        labels:\n          severity: warning\n          service: api\n        annotations:\n          summary: High error rate\n          description: >\n            Error rate exceeds 5% for more than 5 minutes.\n            Investigate API issues or database connectivity.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]`,
                },
              ].map((template) => (
                <button
                  key={template.name}
                  type="button"
                  onClick={() => {
                    setImportYamlContent(template.yaml);
                    setImportFileName(`${template.name} Template`);
                  }}
                  className="group flex items-center gap-3 p-3 rounded-lg border border-sre-border bg-sre-surface/50 hover:bg-sre-surface hover:border-sre-primary/30 transition-all duration-200 text-left"
                >
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-sre-primary/20 to-sre-primary/10 flex items-center justify-center flex-shrink-0">
                    <span className="material-icons text-sre-primary text-sm">
                      {template.name === "Memory Usage"
                        ? "memory"
                        : template.name === "CPU Usage"
                          ? "developer_board"
                          : template.name === "Disk Space"
                            ? "storage"
                            : "dns"}
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
                  const f = e.target.files && e.target.files[0];
                  if (!f) return;
                  try {
                    const txt = await f.text();
                    setImportYamlContent(txt);
                    setImportFileName(f.name || "uploaded.yaml");
                    toast && toast.success && toast.success("YAML loaded");
                  } catch (err) {
                    toast && toast.error && toast.error("Failed to read file");
                  }
                }}
              />
              <span className="material-icons text-sm">file_upload</span>
              Upload YAML
            </label>

            {importFileName && (
              <div className="text-xs text-sre-text-muted ml-2">
                {importFileName}
              </div>
            )}
          </div>

          <textarea
            value={importYamlContent}
            onChange={(e) => {
              setImportYamlContent(e.target.value);
              setImportFileName("");
            }}
            rows={14}
            className="w-full rounded border border-sre-border bg-sre-bg p-3 font-mono text-xs text-sre-text"
            placeholder={`groups:\n  - name: core-services-memory\n    rules:\n      - alert: HighMemoryUsage\n        expr: |\n          (\n            node_memory_MemTotal_bytes\n            - node_memory_MemAvailable_bytes\n          )\n          / node_memory_MemTotal_bytes > 0.80\n        for: 5m\n        labels:\n          severity: warning\n          service: core\n          resource: memory\n        annotations:\n          summary: High memory usage detected\n          description: >\n            Memory usage has exceeded 80% for more than 5 minutes.\n            This may indicate memory leaks, pod overcommitment, or insufficient node sizing.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]\n\n      - alert: CriticalMemoryUsage\n        expr: |\n          (\n            node_memory_MemTotal_bytes\n            - node_memory_MemAvailable_bytes\n          )\n          / node_memory_MemTotal_bytes > 0.92\n        for: 3m\n        labels:\n          severity: critical\n          service: core\n          resource: memory\n        annotations:\n          summary: Critical memory pressure\n          description: >\n            Memory usage is above 92%. OOM events are likely.\n            Immediate investigation required.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]`}
          />

          {importResult && (
            <Card className="p-3">
              <div className="text-sm text-sre-text">
                {importResult.status === "preview"
                  ? `Preview parsed ${importResult.count || 0} rule(s).`
                  : `Imported ${importResult.count || 0} rule(s) (${importResult.created || 0} created, ${importResult.updated || 0} updated).`}
              </div>
            </Card>
          )}

          <div className="flex items-center justify-end gap-2">
            <Button
              variant="secondary"
              onClick={() => setShowImportRulesModal(false)}
            >
              Close
            </Button>
            <Button
              variant="secondary"
              disabled={importRunning || !importYamlContent.trim()}
              onClick={() => handleImportRules({ dryRun: true })}
            >
              {importRunning ? "Working…" : "Preview"}
            </Button>
            <Button
              disabled={importRunning || !importYamlContent.trim()}
              onClick={() => handleImportRules({ dryRun: false })}
            >
              {importRunning ? "Importing…" : "Import"}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Rule Editor Modal */}
      <Modal
        isOpen={showRuleEditor}
        onClose={() => {
          setShowRuleEditor(false);
          setEditingRule(null);
        }}
        title={editingRule ? "Edit Alert Rule" : "Create Alert Rule"}
        size="lg"
        closeOnOverlayClick={false}
      >
        <RuleEditor
          rule={editingRule}
          channels={channels}
          apiKeys={apiKeys}
          availableCorrelationIds={correlationIdOptions}
          onSave={async (data) => {
            const ok = await handleSaveRule(data);
            if (ok) {
              setShowRuleEditor(false);
              setEditingRule(null);
            }
            return ok;
          }}
          onCancel={() => {
            setShowRuleEditor(false);
            setEditingRule(null);
          }}
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
          onSave={(data) => {
            handleCreateSilence(data);
            setShowSilenceForm(false);
          }}
          onCancel={() => setShowSilenceForm(false)}
        />
      </Modal>

      {testDialog.isOpen && (
        <ConfirmModal
          isOpen={testDialog.isOpen}
          title={testDialog.title}
          message={testDialog.message}
          onConfirm={() =>
            setTestDialog({ isOpen: false, title: "", message: "" })
          }
          onCancel={() =>
            setTestDialog({ isOpen: false, title: "", message: "" })
          }
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
  );
}
