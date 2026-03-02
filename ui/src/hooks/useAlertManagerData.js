import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getAlerts,
  getSilences,
  getAlertRules,
  getNotificationChannels,
} from "../api";
import { normalizeRuleForUI } from "../utils/alertmanagerRuleUtils";

export const useAlertManagerData = () => {
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
      const [alertsData, silencesData, rulesData, channelsData] =
        await Promise.all([
          getAlerts().catch(() => []),
          getSilences().catch(() => []),
          getAlertRules().catch(() => []),
          getNotificationChannels().catch(() => []),
        ]);
      if (requestId !== requestIdRef.current) return;
      setAlerts(alertsData);
      setSilences(
        (silencesData || []).filter(
          (s) =>
            !(
              s?.status?.state &&
              String(s.status.state).toLowerCase() === "expired"
            ),
        ),
      );
      setRules(
        Array.isArray(rulesData) ? rulesData.map(normalizeRuleForUI) : [],
      );
      setChannels(channelsData);
    } catch (e) {
      if (requestId !== requestIdRef.current) return;
      setError(e.message || String(e));
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, []);

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
