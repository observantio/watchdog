import { useEffect, useState } from "react";
import {
  fetchHealth,
  getAlerts,
  getLogVolume,
  searchDashboards,
  getSilences,
  getDatasources,
  fetchSystemMetrics,
} from "../api";
import { getVolumeValues } from "../utils/lokiQueryUtils";
import { useAuth } from "../contexts/AuthContext";

export function useDashboardData() {
  const { hasPermission } = useAuth();
  const canReadAlerts = hasPermission("read:alerts");
  const canReadDashboards = hasPermission("read:dashboards");
  const canReadLogs = hasPermission("read:logs");

  // Health state
  const [health, setHealth] = useState(null);
  const [loadingHealth, setLoadingHealth] = useState(true);

  // Alerts state
  const [alertCount, setAlertCount] = useState(null);
  const [loadingAlerts, setLoadingAlerts] = useState(true);

  // Logs state
  const [logVolume, setLogVolume] = useState(null);
  const [logVolumeSeries, setLogVolumeSeries] = useState([]);
  const [loadingLogs, setLoadingLogs] = useState(true);

  // Dashboards state
  const [dashboardCount, setDashboardCount] = useState(null);
  const [loadingDashboards, setLoadingDashboards] = useState(true);

  // Silences state
  const [silenceCount, setSilenceCount] = useState(null);
  const [loadingSilences, setLoadingSilences] = useState(true);

  // Datasources state
  const [datasourceCount, setDatasourceCount] = useState(null);
  const [loadingDatasources, setLoadingDatasources] = useState(true);

  // System metrics state
  const [systemMetrics, setSystemMetrics] = useState(null);
  const [loadingSystemMetrics, setLoadingSystemMetrics] = useState(true);

  const computeLogTotal = (vol) => {
    if (!vol?.data?.result || !Array.isArray(vol.data.result)) return 0;
    let total = 0;
    for (const series of vol.data.result) {
      if (!Array.isArray(series.values)) continue;
      for (const v of series.values) {
        const val = Number(v[1]);
        if (!Number.isNaN(val)) total += val;
      }
    }
    return total;
  };

  useEffect(() => {
    let active = true;
    const nowMs = Date.now();
    const endNs = nowMs * 1000000;
    const startNs = endNs - 60 * 60 * 1000000000;

    // Fetch health
    (async () => {
      try {
        const res = await fetchHealth();
        if (active) setHealth(res);
      } catch {
        if (active) setHealth(null);
      } finally {
        if (active) setLoadingHealth(false);
      }
    })();

    // Fetch alerts
    (async () => {
      if (!canReadAlerts) {
        if (active) setLoadingAlerts(false);
        return;
      }
      try {
        const data = await getAlerts();
        if (active) setAlertCount(Array.isArray(data) ? data.length : 0);
      } catch {
        if (active) setAlertCount(0);
      } finally {
        if (active) setLoadingAlerts(false);
      }
    })();

    // Fetch logs
    (async () => {
      if (!canReadLogs) {
        if (active) {
          setLogVolume(null);
          setLogVolumeSeries([]);
          setLoadingLogs(false);
        }
        return;
      }
      try {
        const vol = await getLogVolume('{service_name=~".+"}', {
          start: Math.floor(startNs),
          end: Math.floor(endNs),
          step: 60,
        });
        let total = 0;
        try {
          total = computeLogTotal(vol);
        } catch {
          // If computing the total fails, default to 0 so the metric displays "0"
          total = 0;
        }
        if (active) {
          setLogVolume(total);
          // store series for LogVolume sparkline
          try {
            const series = getVolumeValues(vol);
            setLogVolumeSeries(series);
          } catch (e) {
            setLogVolumeSeries([]);
          }
        }
      } catch (e) {
        void e;
        // On error fetching logs, show 0 instead of leaving the metric as N/A
        if (active) {
          setLogVolume(0);
          setLogVolumeSeries([]);
        }
      } finally {
        if (active) setLoadingLogs(false);
      }
    })();

    // Fetch dashboards
    (async () => {
      if (!canReadDashboards) {
        if (active) setLoadingDashboards(false);
        return;
      }
      try {
        const data = await searchDashboards();
        if (active) setDashboardCount(Array.isArray(data) ? data.length : 0);
      } catch {
        if (active) setDashboardCount(0);
      } finally {
        if (active) setLoadingDashboards(false);
      }
    })();

    // Fetch silences
    (async () => {
      if (!canReadAlerts) {
        if (active) setLoadingSilences(false);
        return;
      }
      try {
        const data = await getSilences();
        if (active) setSilenceCount(Array.isArray(data) ? data.length : 0);
      } catch {
        if (active) setSilenceCount(0);
      } finally {
        if (active) setLoadingSilences(false);
      }
    })();

    // Fetch datasources
    (async () => {
      if (!canReadDashboards) {
        if (active) setLoadingDatasources(false);
        return;
      }
      try {
        const data = await getDatasources();
        if (active) setDatasourceCount(Array.isArray(data) ? data.length : 0);
      } catch {
        if (active) setDatasourceCount(0);
      } finally {
        if (active) setLoadingDatasources(false);
      }
    })();

    // Fetch system metrics
    (async () => {
      try {
        const data = await fetchSystemMetrics();
        if (active) setSystemMetrics(data);
      } catch {
        if (active) setSystemMetrics(null);
      } finally {
        if (active) setLoadingSystemMetrics(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [canReadAlerts, canReadDashboards, canReadLogs]);

  return {
    // Health
    health,
    loadingHealth,

    // Alerts
    alertCount,
    loadingAlerts,

    // Logs
    logVolume,
    logVolumeSeries,
    loadingLogs,

    // Dashboards
    dashboardCount,
    loadingDashboards,

    // Silences
    silenceCount,
    loadingSilences,

    // Datasources
    datasourceCount,
    loadingDatasources,

    // System metrics
    systemMetrics,
    loadingSystemMetrics,
  };
}
