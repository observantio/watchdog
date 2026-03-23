import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getAlerts,
  getSilences,
  getAlertRules,
  getNotificationChannels,
} from "../api";
import { normalizeRuleForUI } from "../utils/alertmanagerRuleUtils";

export const useAlertManagerData = ({
  showHiddenRules = false,
  showHiddenSilences = false,
  alertFilters = {},
  ruleFilters = {},
} = {}) => {
  const [alerts, setAlerts] = useState([]);
  const [silences, setSilences] = useState([]);
  const [rules, setRules] = useState([]);
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const requestIdRef = useRef(0);

  const loadData = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    setError(null);
    try {
      const settled = await Promise.allSettled([
        getAlerts({
          severity: alertFilters?.severity,
          correlationId: alertFilters?.correlationId,
          label: alertFilters?.label,
        }),
        getSilences({ showHidden: showHiddenSilences }),
        getAlertRules({
          showHidden: showHiddenRules,
          owner: ruleFilters?.owner,
          status: ruleFilters?.status,
          severity: ruleFilters?.severity,
          orgId: ruleFilters?.orgId,
          correlationId: ruleFilters?.correlationId,
        }),
        getNotificationChannels(),
      ]);
      if (requestId !== requestIdRef.current) return;

      const endpointLabels = ["alerts", "silences", "rules", "channels"];
      const failed = settled
        .map((result, idx) => ({ result, label: endpointLabels[idx] }))
        .filter(({ result }) => result.status === "rejected")
        .map(({ label, result }) => {
          const reason = result.reason;
          const message =
            reason?.message || reason?.body?.message || "request failed";
          return `${label} (${message})`;
        });

      if (settled[0].status === "fulfilled") {
        setAlerts(Array.isArray(settled[0].value) ? settled[0].value : []);
      }
      if (settled[1].status === "fulfilled") {
        const rawSilences = Array.isArray(settled[1].value)
          ? settled[1].value
          : [];
        setSilences(
          rawSilences.filter(
            (s) =>
              !(
                s?.status?.state &&
                String(s.status.state).toLowerCase() === "expired"
              ),
          ),
        );
      }
      if (settled[2].status === "fulfilled") {
        const rawRules = Array.isArray(settled[2].value) ? settled[2].value : [];
        setRules(rawRules.map(normalizeRuleForUI));
      }
      if (settled[3].status === "fulfilled") {
        setChannels(Array.isArray(settled[3].value) ? settled[3].value : []);
      }

      if (failed.length > 0) {
        setError(`Failed to load ${failed.join(", ")}`);
      }
    } catch (e) {
      if (requestId !== requestIdRef.current) return;
      setError(e.message || String(e));
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [
    showHiddenRules,
    showHiddenSilences,
    alertFilters?.severity,
    alertFilters?.correlationId,
    alertFilters?.label,
    ruleFilters?.owner,
    ruleFilters?.status,
    ruleFilters?.severity,
    ruleFilters?.orgId,
    ruleFilters?.correlationId,
  ]);

  useEffect(() => {
    loadData();
    return () => {
      requestIdRef.current += 1;
    };
  }, [loadData]);

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

  return {
    alerts,
    silences,
    rules,
    channels,
    loading,
    error,
    stats,
    reloadData: loadData,
    setError,
  };
};
