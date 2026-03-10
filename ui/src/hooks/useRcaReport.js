import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getRcaJob,
  getRcaReportById,
  getRcaJobResult,
  fetchRcaBayesian,
  fetchRcaCorrelate,
  fetchRcaForecast,
  fetchRcaGranger,
  fetchRcaSloBurn,
  fetchRcaTopology,
  getRcaDeployments,
  getRcaMlWeights,
} from "../api";

function deriveRootService(report) {
  if (
    Array.isArray(report?.service_latency) &&
    report.service_latency.length > 0
  ) {
    return report.service_latency[0].service;
  }
  if (
    Array.isArray(report?.error_propagation) &&
    report.error_propagation.length > 0
  ) {
    return report.error_propagation[0].source_service;
  }
  return "";
}

function basePayloadFromReport(report) {
  return {
    start: report?.start,
    end: report?.end,
    step: "15s",
    services: Array.from(
      new Set(
        (report?.service_latency || []).map((s) => s.service).filter(Boolean),
      ),
    ).slice(0, 5),
    metric_queries: [],
    log_query: null,
  };
}

const EMPTY_INSIGHTS = {
  correlate: null,
  topology: null,
  slo: null,
  forecast: null,
  granger: null,
  bayesian: null,
  mlWeights: null,
  deployments: null,
};

const EMPTY_INSIGHT_ERRORS = {
  correlate: null,
  topology: null,
  slo: null,
  forecast: null,
  granger: null,
  bayesian: null,
  mlWeights: null,
  deployments: null,
};

const TERMINAL_JOB_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
  "deleted",
]);
const FAILED_JOB_STATUSES = new Set(["failed", "cancelled", "deleted"]);
const REPORT_POLL_MS = 5000;

const TAB_INSIGHT_KEYS = {
  topology: ["topology"],
  causal: ["correlate", "granger", "bayesian", "mlWeights", "deployments"],
  "forecast-slo": ["forecast", "slo"],
};

function normalizeEmbeddedInsights(reportData) {
  return {
    ...EMPTY_INSIGHTS,
    topology: reportData?.topology || reportData?.blast_radius || null,
    slo: reportData?.slo || reportData?.slo_burn || null,
    forecast: reportData?.forecast || null,
    granger: reportData?.granger || null,
    bayesian: reportData?.bayesian || null,
    correlate: reportData?.correlate || null,
    mlWeights: reportData?.ml_weights || reportData?.mlWeights || null,
    deployments: reportData?.deployments || null,
  };
}

function isIncompleteJobMessage(err) {
  const message = String(err?.body?.detail || err?.message || "").toLowerCase();
  return (
    Number(err?.status) === 409 ||
    message.includes("not completed yet") ||
    message.includes("not ready") ||
    message.includes("not available")
  );
}

function isReportNotFoundError(err) {
  const message = String(err?.body?.detail || err?.message || "").toLowerCase();
  return Number(err?.status) === 404 || message.includes("report not found");
}

function normalizeJobStatus(value) {
  return String(value || "").toLowerCase();
}

export function useRcaReport(
  selectedJobId,
  selectedJob,
  reportIdOverride = null,
  options = {},
) {
  const { enableInsights = false, activeInsightTab = "summary" } = options;
  const requestSeq = useRef(0);
  const insightRequestRef = useRef(0);
  const [loadingPrimaryReport, setLoadingPrimaryReport] = useState(false);
  const [loadingInsights, setLoadingInsights] = useState(false);
  const [reportError, setReportError] = useState(null);
  const [reportErrorStatus, setReportErrorStatus] = useState(null);
  const [report, setReport] = useState(null);
  const [reportMeta, setReportMeta] = useState(null);
  const [insights, setInsights] = useState(EMPTY_INSIGHTS);
  const [insightErrors, setInsightErrors] = useState(EMPTY_INSIGHT_ERRORS);
  const insightsRef = useRef(EMPTY_INSIGHTS);
  const insightErrorsRef = useRef(EMPTY_INSIGHT_ERRORS);
  const deferredReportIdsRef = useRef(new Set());

  useEffect(() => {
    insightsRef.current = insights;
  }, [insights]);

  useEffect(() => {
    insightErrorsRef.current = insightErrors;
  }, [insightErrors]);

  const loadInsightsForTab = useCallback(async (reportData, seq, tab) => {
    if (!reportData?.start || !reportData?.end) return;
    const needed = TAB_INSIGHT_KEYS[tab] || [];
    if (needed.length === 0) return;

    const currentInsights = insightsRef.current;
    const currentErrors = insightErrorsRef.current;
    const missing = needed.filter(
      (key) => !currentInsights[key] && !currentErrors[key],
    );
    if (missing.length === 0) return;

    const basePayload = basePayloadFromReport(reportData);
    const rootService = deriveRootService(reportData);
    const calls = [];

    if (missing.includes("forecast")) {
      calls.push({
        key: "forecast",
        req: fetchRcaForecast(basePayload, { limit: 100 }),
      });
    }
    if (missing.includes("correlate")) {
      calls.push({
        key: "correlate",
        req: fetchRcaCorrelate({
          ...basePayload,
          window_seconds: 60,
        }),
      });
    }
    if (missing.includes("granger")) {
      calls.push({
        key: "granger",
        req: fetchRcaGranger(basePayload, {
          limit: 100,
          min_strength: 0.05,
          max_series: 25,
        }),
      });
    }
    if (missing.includes("bayesian")) {
      calls.push({
        key: "bayesian",
        req: fetchRcaBayesian({
          ...basePayload,
          apdex_threshold_ms: 500,
          slo_target: 0.999,
          correlation_window_seconds: 60,
          forecast_horizon_seconds: 1800,
        }),
      });
    }
    if (missing.includes("mlWeights")) {
      calls.push({ key: "mlWeights", req: getRcaMlWeights() });
    }
    if (missing.includes("deployments")) {
      calls.push({ key: "deployments", req: getRcaDeployments() });
    }
    if (missing.includes("topology") && rootService) {
      calls.push({
        key: "topology",
        req: fetchRcaTopology({
          start: reportData.start,
          end: reportData.end,
          root_service: rootService,
          max_depth: 6,
        }),
      });
    }
    if (missing.includes("slo") && rootService) {
      calls.push({
        key: "slo",
        req: fetchRcaSloBurn({
          service: rootService,
          start: reportData.start,
          end: reportData.end,
          step: "15s",
          target_availability: 0.999,
        }),
      });
    }
    if (calls.length === 0) return;

    const insightSeq = insightRequestRef.current + 1;
    insightRequestRef.current = insightSeq;
    setLoadingInsights(true);

    const settled = await Promise.allSettled(calls.map((entry) => entry.req));
    if (seq !== requestSeq.current || insightSeq !== insightRequestRef.current)
      return;

    const nextInsights = {};
    const nextErrors = {};
    calls.forEach((entry, index) => {
      const result = settled[index];
      if (result.status === "fulfilled") {
        nextInsights[entry.key] = result.value;
        nextErrors[entry.key] = null;
      } else {
        nextErrors[entry.key] =
          result.reason?.message || `Failed to load ${entry.key}`;
      }
    });

    setInsights((prev) => {
      const merged = { ...prev, ...nextInsights };
      insightsRef.current = merged;
      return merged;
    });
    setInsightErrors((prev) => {
      const merged = { ...prev, ...nextErrors };
      insightErrorsRef.current = merged;
      return merged;
    });
    setLoadingInsights(false);
  }, []);

  const reset = useCallback(() => {
    setReport(null);
    setReportMeta(null);
    setInsights(EMPTY_INSIGHTS);
    setInsightErrors(EMPTY_INSIGHT_ERRORS);
    insightsRef.current = EMPTY_INSIGHTS;
    insightErrorsRef.current = EMPTY_INSIGHT_ERRORS;
    setLoadingInsights(false);
  }, []);

  const clearReportData = useCallback(() => {
    setReport(null);
    setInsights(EMPTY_INSIGHTS);
    setInsightErrors(EMPTY_INSIGHT_ERRORS);
    insightsRef.current = EMPTY_INSIGHTS;
    insightErrorsRef.current = EMPTY_INSIGHT_ERRORS;
    setLoadingInsights(false);
  }, []);

  const applyLoadedReport = useCallback(
    (reportData, reportId) => {
      if (reportId) {
        deferredReportIdsRef.current.delete(reportId);
      }
      setReport(reportData);
      const initialInsights = normalizeEmbeddedInsights(reportData);
      setInsights(initialInsights);
      setInsightErrors(EMPTY_INSIGHT_ERRORS);
      insightsRef.current = initialInsights;
      insightErrorsRef.current = EMPTY_INSIGHT_ERRORS;
      setLoadingInsights(false);
    },
    [],
  );

  const loadReport = useCallback(async () => {
    const seq = requestSeq.current + 1;
    requestSeq.current = seq;
    const selectedReportId = String(selectedJob?.report_id || "").trim();

    if (
      !reportIdOverride &&
      (!selectedJobId || selectedJobId.startsWith("pending-"))
    ) {
      reset();
      setReportError(null);
      setLoadingPrimaryReport(false);
      return;
    }

    setLoadingPrimaryReport(true);
    setReportError(null);
    setReportErrorStatus(null);
    try {
      let liveJob = null;
      if (!reportIdOverride && selectedJobId && !selectedJobId.startsWith("pending-")) {
        try {
          liveJob = await getRcaJob(selectedJobId);
        } catch {
          liveJob = null;
        }
      }
      const effectiveReportId = String(
        liveJob?.report_id || selectedReportId || "",
      ).trim();
      const shouldPreferJobResult =
        !reportIdOverride &&
        effectiveReportId &&
        deferredReportIdsRef.current.has(effectiveReportId);

      let res;
      if (reportIdOverride) {
        res = await getRcaReportById(reportIdOverride);
      } else if (effectiveReportId && !shouldPreferJobResult) {
        // Prefer fetching by report id when available; it is more stable than
        // job-result during status propagation delays.
        try {
          res = await getRcaReportById(effectiveReportId);
        } catch (err) {
          if (!isIncompleteJobMessage(err) && !isReportNotFoundError(err)) {
            throw err;
          }
          deferredReportIdsRef.current.add(effectiveReportId);
          res = await getRcaJobResult(selectedJobId);
        }
      } else {
        res = await getRcaJobResult(selectedJobId);
      }
      if (
        !reportIdOverride &&
        (!res || (res?.status == null && res?.result == null))
      ) {
        res = await getRcaJobResult(selectedJobId);
      }
      if (seq !== requestSeq.current) return;

      setReportMeta({
        job_id: res?.job_id || liveJob?.job_id,
        report_id: res?.report_id || liveJob?.report_id,
        status: res?.status || liveJob?.status,
        tenant_id: res?.tenant_id || liveJob?.tenant_id,
        requested_by: res?.requested_by || liveJob?.requested_by,
      });
      if (res?.status !== "completed" || !res?.result) {
        clearReportData();
      } else {
        applyLoadedReport(res.result, effectiveReportId);
        setLoadingPrimaryReport(false);
        return;
      }
    } catch (err) {
      if (seq !== requestSeq.current) return;
      if (isIncompleteJobMessage(err) || isReportNotFoundError(err)) {
        setReportError(null);
        setReportErrorStatus(isReportNotFoundError(err) ? 404 : null);
      } else {
        setReportError(err?.message || "Failed to load RCA report");
        setReportErrorStatus(err?.status || null);
      }
      reset();
    } finally {
      if (seq === requestSeq.current) {
        setLoadingPrimaryReport(false);
      }
    }
  }, [
    applyLoadedReport,
    clearReportData,
    reportIdOverride,
    reset,
    selectedJob,
    selectedJobId,
  ]);

  useEffect(() => {
    if (reportIdOverride) {
      loadReport();
      return;
    }

    if (!selectedJobId) {
      requestSeq.current += 1;
      reset();
      setReportError(null);
      setReportErrorStatus(null);
      return;
    }
    const normalizedStatus = normalizeJobStatus(selectedJob?.status);
    if (
      normalizedStatus === "completed" ||
      !TERMINAL_JOB_STATUSES.has(normalizedStatus)
    ) {
      loadReport();
    } else if (FAILED_JOB_STATUSES.has(normalizedStatus)) {
      requestSeq.current += 1;
      reset();
      setReportError(selectedJob?.error || "RCA job did not complete");
      setReportErrorStatus(null);
    }
  }, [loadReport, reportIdOverride, reset, selectedJob, selectedJobId]);

  useEffect(() => {
    if (reportIdOverride || !selectedJobId) return undefined;
    const normalizedStatus = normalizeJobStatus(selectedJob?.status);
    const shouldAwaitCompletedPayload =
      normalizedStatus === "completed" && !report;
    if (FAILED_JOB_STATUSES.has(normalizedStatus)) {
      return undefined;
    }
    if (!shouldAwaitCompletedPayload && normalizedStatus === "completed") {
      return undefined;
    }

    const poll = () => {
      if (typeof document !== "undefined" && document.hidden) return;
      loadReport();
    };
    const timer = setInterval(() => {
      poll();
    }, REPORT_POLL_MS);

    const onVisibilityChange = () => {
      if (typeof document !== "undefined" && !document.hidden) {
        poll();
      }
    };
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisibilityChange);
    }
    return () => {
      clearInterval(timer);
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVisibilityChange);
      }
    };
  }, [loadReport, report, reportIdOverride, selectedJob?.status, selectedJobId]);

  useEffect(() => {
    if (!enableInsights || !report) return;
    void loadInsightsForTab(report, requestSeq.current, activeInsightTab);
  }, [activeInsightTab, enableInsights, loadInsightsForTab, report]);

  const hasReport = useMemo(() => Boolean(report), [report]);

  return {
    loadingPrimaryReport,
    loadingInsights,
    loadingReport: loadingPrimaryReport || loadingInsights,
    reportError,
    reportErrorStatus,
    report,
    reportMeta,
    insights,
    insightErrors,
    hasReport,
    reloadReport: loadReport,
  };
}
