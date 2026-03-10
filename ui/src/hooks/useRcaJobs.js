import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createRcaAnalyzeJob,
  deleteRcaReport,
  getRcaJob,
  listRcaJobs,
} from "../api";
import { useToast } from "../contexts/ToastContext";

const JOB_POLL_MS = 5000;
const RECONCILE_LOCAL_JOBS_LIMIT = 10;
const ACTIVE_JOBS_STORAGE_KEY = "rcaPage.activeJobs";
const DELETED_REPORTS_STORAGE_KEY = "rcaPage.deletedReportIds";
const TERMINAL_JOB_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
  "deleted",
]);

function isTerminalStatus(value) {
  return TERMINAL_JOB_STATUSES.has(String(value || "").toLowerCase());
}

function hasActiveJobs(items) {
  return (items || []).some((job) => !isTerminalStatus(job?.status));
}

function mergeJobs(authoritative, local = []) {
  const byId = new Map();
  for (const job of authoritative || []) {
    if (job?.job_id) byId.set(job.job_id, job);
  }

  for (const job of local || []) {
    if (!job?.job_id) continue;
    if (byId.has(job.job_id)) continue;
    if (!isTerminalStatus(job.status)) byId.set(job.job_id, job);
  }

  return Array.from(byId.values())
    .sort((a, b) => {
      const aTime =
        Date.parse(a?.created_at || a?.started_at || a?.finished_at || "") || 0;
      const bTime =
        Date.parse(b?.created_at || b?.started_at || b?.finished_at || "") || 0;
      return bTime - aTime;
    })
    .slice(0, 30);
}

function loadActiveJobsFromStorage() {
  try {
    const raw = localStorage.getItem(ACTIVE_JOBS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (job) => job && job.job_id && !isTerminalStatus(job.status),
    );
  } catch {
    return [];
  }
}

function persistActiveJobsToStorage(items) {
  try {
    const active = (items || [])
      .filter((job) => job?.job_id && !isTerminalStatus(job?.status))
      .slice(0, 30);
    if (active.length === 0) {
      localStorage.removeItem(ACTIVE_JOBS_STORAGE_KEY);
      return;
    }
    localStorage.setItem(ACTIVE_JOBS_STORAGE_KEY, JSON.stringify(active));
  } catch {
    // ignore storage errors
  }
}

function loadDeletedReportIdsFromStorage() {
  try {
    const raw = localStorage.getItem(DELETED_REPORTS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((id) => String(id || "").trim())
      .filter(Boolean)
      .slice(0, 200);
  } catch {
    return [];
  }
}

function persistDeletedReportIdsToStorage(reportIds) {
  try {
    const normalized = Array.from(
      new Set((reportIds || []).map((id) => String(id || "").trim()).filter(Boolean)),
    ).slice(0, 200);
    if (normalized.length === 0) {
      localStorage.removeItem(DELETED_REPORTS_STORAGE_KEY);
      return;
    }
    localStorage.setItem(DELETED_REPORTS_STORAGE_KEY, JSON.stringify(normalized));
  } catch {
    // ignore storage errors
  }
}

function filterDeletedJobs(items, deletedReportIds) {
  if (!Array.isArray(items) || items.length === 0) return [];
  const deleted = new Set(
    (deletedReportIds || []).map((id) => String(id || "").trim()).filter(Boolean),
  );
  return items.filter((job) => {
    const reportId = String(job?.report_id || "").trim();
    if (reportId && deleted.has(reportId)) return false;
    return !isTerminalStatus(job?.status) || String(job?.status || "").toLowerCase() !== "deleted";
  });
}

export function useRcaJobs() {
  const toast = useToast();
  const [jobs, setJobs] = useState(() => loadActiveJobsFromStorage());
  const jobsRef = useRef(jobs);
  const [deletedReportIds, setDeletedReportIds] = useState(() =>
    loadDeletedReportIdsFromStorage(),
  );
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [creatingJob, setCreatingJob] = useState(false);
  const [deletingReport, setDeletingReport] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState(null);

  useEffect(() => {
    jobsRef.current = jobs;
  }, [jobs]);

  const refreshJobs = useCallback(async () => {
    setLoadingJobs(true);
    try {
      const res = await listRcaJobs({ limit: 30 });
      const items = filterDeletedJobs(
        Array.isArray(res?.items) ? res.items : [],
        deletedReportIds,
      );
      const authoritativeJobIds = new Set(
        items.map((job) => String(job?.job_id || "")).filter(Boolean),
      );

      const localOnlyActiveIds = Array.from(
        new Set(
          jobsRef.current
            // use latest in-memory jobs to reconcile stale local queue entries
            .filter((job) => {
              const jobId = String(job?.job_id || "");
              if (!jobId || jobId.startsWith("pending-")) return false;
              if (isTerminalStatus(job?.status)) return false;
              return !authoritativeJobIds.has(jobId);
            })
            .map((job) => String(job.job_id)),
        ),
      ).slice(0, RECONCILE_LOCAL_JOBS_LIMIT);

      if (localOnlyActiveIds.length > 0) {
        const reconciled = await Promise.allSettled(
          localOnlyActiveIds.map((jobId) => getRcaJob(jobId)),
        );
        for (const result of reconciled) {
          if (result.status !== "fulfilled") continue;
          const job = result.value;
          const jobId = String(job?.job_id || "");
          if (!jobId) continue;
          if (authoritativeJobIds.has(jobId)) continue;
          items.push(job);
        }
      }

      setJobs((prev) => {
        const merged = mergeJobs(items, prev);
        if (
          merged.length > 0 &&
          (!selectedJobId ||
            !merged.some((job) => job.job_id === selectedJobId))
        ) {
          setSelectedJobId(merged[0].job_id);
        }
        return merged;
      });
    } catch (err) {
      toast?.error?.(err?.message || "Failed to load RCA jobs");
    } finally {
      setLoadingJobs(false);
    }
  }, [deletedReportIds, selectedJobId, toast]);

  useEffect(() => {
    refreshJobs();
  }, [refreshJobs]);

  useEffect(() => {
    persistActiveJobsToStorage(jobs);
  }, [jobs]);

  useEffect(() => {
    persistDeletedReportIdsToStorage(deletedReportIds);
  }, [deletedReportIds]);

  useEffect(() => {
    if (!hasActiveJobs(jobs)) return undefined;
    const poll = () => {
      if (typeof document !== "undefined" && document.hidden) return;
      refreshJobs();
    };
    const timer = setInterval(() => {
      poll();
    }, JOB_POLL_MS);
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
  }, [jobs, refreshJobs]);

  const createJob = useCallback(
    async (payload) => {
      setCreatingJob(true);
      const optimisticId = `pending-${Date.now()}`;
      const optimistic = {
        job_id: optimisticId,
        report_id: `pending-report-${Date.now()}`,
        status: "queued",
        created_at: new Date().toISOString(),
        started_at: null,
        finished_at: null,
        duration_ms: null,
        error: null,
        summary_preview: "Submitting RCA analysis request...",
        requested_by: "me",
        tenant_id: "current",
      };
      setJobs((prev) => [optimistic, ...prev].slice(0, 30));
      setSelectedJobId(optimisticId);

      try {
        const created = await createRcaAnalyzeJob(payload);
        setJobs((prev) => {
          const withoutOptimistic = prev.filter(
            (job) => job.job_id !== optimisticId,
          );
          return [created, ...withoutOptimistic].slice(0, 30);
        });
        setSelectedJobId(created.job_id);
        // Pull authoritative state from server immediately so queued/running
        // transitions are reflected without requiring a full page reload.
        await refreshJobs();
        toast?.success?.("RCA analysis job created");
        return created;
      } catch (err) {
        setJobs((prev) => prev.filter((job) => job.job_id !== optimisticId));
        toast?.error?.(err?.message || "Failed to create RCA job");
        throw err;
      } finally {
        setCreatingJob(false);
      }
    },
    [refreshJobs, toast],
  );

  const removeJobByReportId = useCallback(
    (reportId) => {
      setJobs((prev) => {
        const next = prev.filter((job) => job.report_id !== reportId);
        if (
          selectedJobId &&
          !next.some((job) => job.job_id === selectedJobId)
        ) {
          setSelectedJobId(next[0]?.job_id || null);
        }
        return next;
      });
    },
    [selectedJobId],
  );

  const deleteReportById = useCallback(
    async (reportId) => {
      setDeletingReport(true);
      try {
        await deleteRcaReport(reportId);
        setDeletedReportIds((prev) =>
          prev.includes(reportId) ? prev : [reportId, ...prev].slice(0, 200),
        );
        removeJobByReportId(reportId);
        toast?.success?.("RCA report deleted");
      } catch (err) {
        toast?.error?.(err?.message || "Failed to delete RCA report");
        throw err;
      } finally {
        setDeletingReport(false);
      }
    },
    [removeJobByReportId, toast],
  );

  const selectedJob = useMemo(
    () => jobs.find((job) => job.job_id === selectedJobId) || null,
    [jobs, selectedJobId],
  );

  return {
    jobs,
    loadingJobs,
    creatingJob,
    deletingReport,
    selectedJobId,
    selectedJob,
    setSelectedJobId,
    createJob,
    deleteReportById,
    removeJobByReportId,
    refreshJobs,
  };
}
