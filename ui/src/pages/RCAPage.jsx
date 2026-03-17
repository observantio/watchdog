import { useEffect, useMemo, useRef, useState } from "react";
import { useLocalStorage } from "../hooks";
import { getRcaAnalyzeConfigTemplate } from "../api";
import PageHeader from "../components/ui/PageHeader";
import { Alert, Button, Card, Spinner } from "../components/ui";
import ConfirmModal from "../components/ConfirmModal";
import { useRcaJobs } from "../hooks/useRcaJobs";
import { useRcaReport } from "../hooks/useRcaReport";
import { useAuth } from "../contexts/AuthContext";
import RcaJobComposer from "../components/rca/RcaJobComposer";
import RcaJobQueuePanel from "../components/rca/RcaJobQueuePanel";
import RcaReportSummary from "../components/rca/RcaReportSummary";
import RcaRootCauseTable from "../components/rca/RcaRootCauseTable";
import RcaAnomalyPanels from "../components/rca/RcaAnomalyPanels";
import RcaClusterPanel from "../components/rca/RcaClusterPanel";
import RcaTopologyPanel from "../components/rca/RcaTopologyPanel";
import RcaCausalPanel from "../components/rca/RcaCausalPanel";
import RcaForecastSloPanel from "../components/rca/RcaForecastSloPanel";
import RcaWarningsPanel from "../components/rca/RcaWarningsPanel";
import RcaReportModal from "../components/rca/RcaReportModal";
import RcaLookup from "../components/rca/RcaLookup";

const TAB_STORAGE_KEY = "rcaPage.activeTab";
const JOB_STORAGE_KEY = "rcaPage.selectedJobId";
const REPORT_STORAGE_KEY = "rcaPage.reportLookupId";
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const TABS = [
  { key: "summary", label: "Summary" },
  { key: "root-causes", label: "Root Causes" },
  { key: "anomalies", label: "Anomalies" },
  { key: "clusters", label: "Clusters" },
  { key: "topology", label: "Topology" },
  { key: "causal", label: "Causal" },
  { key: "forecast-slo", label: "Forecast/SLO" },
  { key: "warnings", label: "Warnings" },
];

export default function RCAPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useLocalStorage(TAB_STORAGE_KEY, "summary");
  const [reportLookupInput, setReportLookupInput] = useState("");
  const [reportLookupId, setReportLookupId] = useState(null);
  const [lookupError, setLookupError] = useState(null);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [viewModalOpen, setViewModalOpen] = useState(false);
  const [didRestoreSelectedJob, setDidRestoreSelectedJob] = useState(false);
  const modalReloadedForJobRef = useRef(null);

  const {
    jobs,
    loadingJobs,
    creatingJob,
    deletingReport,
    selectedJobId,
    selectedJob,
    setSelectedJobId,
    createJob,
    refreshJobs,
    deleteReportById,
    removeJobByReportId,
  } = useRcaJobs();

  const handleView = (job) => {
    if (!job || !job.job_id) return;
    setReportLookupId(null);
    setSelectedJobId(job.job_id);
    setViewModalOpen(true);
  };
  const {
    loadingPrimaryReport,
    loadingInsights,
    loadingReport,
    reportError,
    reportErrorStatus,
    report,
    reportMeta,
    insights,
    insightErrors,
    hasReport,
    reloadReport,
  } = useRcaReport(selectedJobId, selectedJob, reportLookupId, {
    enableInsights: viewModalOpen,
    activeInsightTab: activeTab,
  });

  const reportStats = useMemo(() => {
    if (!report) return null;
    return [
      {
        label: "Overall Severity",
        value: String(report.overall_severity || "UNKNOWN").toUpperCase(),
        color:
          report.overall_severity === "critical" ||
          report.overall_severity === "high"
            ? "text-sre-error"
            : report.overall_severity === "medium"
              ? "text-sre-warning"
              : "text-sre-success",
      },
      {
        label: "Metric Anomalies",
        value: report.metric_anomalies?.length || 0,
        color: "text-sre-text",
      },
      {
        label: "Root Causes",
        value: report.root_causes?.length || 0,
        color: "text-sre-text",
      },
      {
        label: "Duration (s)",
        value: report.duration_seconds || 0,
        color: "text-sre-text",
      },
    ];
  }, [report]);

  const selectedReportId =
    reportMeta?.report_id || selectedJob?.report_id || null;
  const ownerUserId = reportMeta?.requested_by || selectedJob?.requested_by;
  const currentUserId = user?.id || user?.user_id || null;
  const canDelete = Boolean(
    selectedReportId && ownerUserId && currentUserId === ownerUserId,
  );
  useEffect(() => {
    if (!selectedJobId) return;
    try {
      localStorage.setItem(JOB_STORAGE_KEY, selectedJobId);
    } catch {
      // ignore
    }
  }, [selectedJobId]);

  useEffect(() => {
    if (didRestoreSelectedJob) return;
    try {
      const stored = localStorage.getItem(JOB_STORAGE_KEY);
      if (stored && jobs.some((j) => j.job_id === stored)) {
        setSelectedJobId(stored);
      }
    } catch {
      // ignore
    } finally {
      setDidRestoreSelectedJob(true);
    }
  }, [didRestoreSelectedJob, jobs, setSelectedJobId]);

  useEffect(() => {
    if (!jobs.length) return;

    if (selectedJobId && !jobs.some((j) => j.job_id === selectedJobId)) {
      setSelectedJobId(null);
      try {
        localStorage.removeItem(JOB_STORAGE_KEY);
      } catch {
        // ignore
      }
      return;
    }

    try {
      const stored = localStorage.getItem(JOB_STORAGE_KEY);
      if (stored && !jobs.some((j) => j.job_id === stored)) {
        localStorage.removeItem(JOB_STORAGE_KEY);
      }
    } catch {
      // ignore
    }
  }, [jobs, selectedJobId, setSelectedJobId]);

  useEffect(() => {
    try {
      localStorage.removeItem(REPORT_STORAGE_KEY);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (reportLookupId) {
      setViewModalOpen(true);
    }
  }, [reportLookupId]);

  useEffect(() => {
    if (!viewModalOpen) {
      modalReloadedForJobRef.current = null;
      return;
    }
    if (!selectedJobId) return;
    if (hasReport || loadingPrimaryReport) return;
    if (modalReloadedForJobRef.current === selectedJobId) return;
    modalReloadedForJobRef.current = selectedJobId;
    void reloadReport();
  }, [
    viewModalOpen,
    selectedJobId,
    hasReport,
    loadingPrimaryReport,
    reloadReport,
  ]);

  useEffect(() => {
    if (reportErrorStatus === 404 && reportLookupId) {
      setReportLookupInput("");
      setReportLookupId(null);
      setViewModalOpen(false);
    }
  }, [
    reportErrorStatus,
    reportLookupId,
    setReportLookupInput,
    setReportLookupId,
  ]);

  async function handleDeleteReport() {
    if (!selectedReportId) return;
    await deleteReportById(selectedReportId);
    setConfirmDeleteOpen(false);
    setReportLookupId(null);
    setReportLookupInput("");
    removeJobByReportId(selectedReportId);
    await refreshJobs();
  }

  function handleLookupReport() {
    const value = reportLookupInput.trim();
    if (!value) {
      setReportLookupId(null);
      setLookupError(null);
      return;
    }
    if (!UUID_RE.test(value)) {
      setLookupError("Report ID must be a valid UUID");
      return;
    }
    setLookupError(null);
    setSelectedJobId(null);
    setReportLookupId(value);
    setViewModalOpen(true);
  }

  function handleClearLookup() {
    setReportLookupInput("");
    setReportLookupId(null);
    setLookupError(null);
  }

  function renderActiveTab(opts = {}) {
    if (!hasReport) {
      return (
        <Card className="border border-sre-border p-6 text-center">
          <p className="text-sm text-sre-text-muted">
            Select a completed RCA job or look up a report ID to view report
            details.
          </p>
        </Card>
      );
    }

    const tabMap = {
      summary: () => (
        <RcaReportSummary report={report} compact={opts.compact} />
      ),
      "root-causes": () => (
        <RcaRootCauseTable report={report} compact={opts.compact} />
      ),
      anomalies: () => (
        <RcaAnomalyPanels report={report} compact={opts.compact} />
      ),
      clusters: () => (
        <RcaClusterPanel report={report} compact={opts.compact} />
      ),
      topology: () => {
        if (loadingInsights && !insights.topology) {
          return (
            <Card className="border border-sre-border p-6 flex items-center justify-center">
              <Spinner />
            </Card>
          );
        }
        if (insightErrors?.topology)
          return <Alert variant="error">{insightErrors.topology}</Alert>;
        return (
          <RcaTopologyPanel
            topology={insights.topology}
            compact={opts.compact}
          />
        );
      },
      causal: () => {
        if (
          loadingInsights &&
          !insights.correlate &&
          !insights.granger &&
          !insights.bayesian
        ) {
          return (
            <Card className="border border-sre-border p-6 flex items-center justify-center">
              <Spinner />
            </Card>
          );
        }
        if (
          insightErrors?.correlate ||
          insightErrors?.granger ||
          insightErrors?.bayesian
        )
          return (
            <Alert variant="error">
              {insightErrors.correlate ||
                insightErrors.granger ||
                insightErrors.bayesian}
            </Alert>
          );
        return (
          <RcaCausalPanel
            correlate={insights.correlate}
            granger={insights.granger}
            bayesian={insights.bayesian}
            mlWeights={insights.mlWeights}
            deployments={insights.deployments}
            compact={opts.compact}
          />
        );
      },
      "forecast-slo": () => {
        if (loadingInsights && !insights.forecast && !insights.slo) {
          return (
            <Card className="border border-sre-border p-6 flex items-center justify-center">
              <Spinner />
            </Card>
          );
        }
        if (insightErrors?.forecast || insightErrors?.slo)
          return (
            <Alert variant="error">
              {insightErrors.forecast || insightErrors.slo}
            </Alert>
          );
        return (
          <RcaForecastSloPanel
            report={report}
            forecast={insights.forecast}
            slo={insights.slo}
            compact={opts.compact}
          />
        );
      },
      warnings: () => (
        <RcaWarningsPanel report={report} compact={opts.compact} />
      ), 
    };

    const renderer = tabMap[activeTab] || tabMap.summary;
    return renderer();
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon="psychology"
        title="AI Root Cause Analysis (RCA)"
        subtitle="Generate, find, and manage tenant-scoped RCA reports through Watchdog."
      >
        <Button variant="secondary" size="sm" onClick={refreshJobs}>
          Refresh Jobs
        </Button>
      </PageHeader>

      {report && (
        <div className="mb-6">
          <span className="text-xs text-sre-text-muted">
            Based on the previous RCA job you ran
          </span>
          {reportStats && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
              {reportStats.map((stat) => (
                <Card
                  key={stat.label}
                  className="p-4 relative overflow-visible bg-gradient-to-br from-sre-surface to-sre-surface/80 border-2 border-sre-border/50 hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm"
                >
                  <div className="text-sre-text-muted text-xs mb-1">
                    {stat.label}
                  </div>
                  <div className={`text-2xl font-bold ${stat.color}`}>
                    {stat.value}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
      <section className="space-y-3">
        <RcaJobComposer
          onCreate={createJob}
          onDownloadTemplate={getRcaAnalyzeConfigTemplate}
          creating={creatingJob}
        />
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-12 border-t border-sre-border pt-6 mt-6 xl:flex xl:gap-8">
        <div className="xl:w-1/3 flex flex-col">
          <RcaLookup
            value={reportLookupInput}
            onChange={(e) => setReportLookupInput(e.target.value)}
            onFind={handleLookupReport}
            onClear={handleClearLookup}
            error={lookupError}
          />
        </div>

        <div className="xl:w-2/3 flex flex-col mt-6 xl:mt-0">
          <RcaJobQueuePanel
            jobs={jobs}
            loading={loadingJobs}
            selectedJobId={selectedJobId}
            onSelectJob={(id) => {
              setReportLookupId(null);
              setSelectedJobId(id);
            }}
            onReload={reloadReport}
            onDelete={() => setConfirmDeleteOpen(true)}
            onView={handleView}
            deletingReport={deletingReport}
            canDelete={canDelete}
          />
        </div>
      </section>

      {/* modal for viewing report details */}
      <RcaReportModal
        isOpen={viewModalOpen}
        onClose={() => setViewModalOpen(false)}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        loadingPrimaryReport={loadingPrimaryReport}
        loadingReport={loadingReport}
        hasReport={hasReport}
        renderActiveTab={renderActiveTab}
        tabs={TABS}
      />

      {reportError && <Alert variant="error">{reportError}</Alert>}
      <ConfirmModal
        isOpen={confirmDeleteOpen}
        title="Delete RCA Report?"
        message="This removes the report payload from storage and hides it from listings."
        confirmText="Delete"
        onConfirm={handleDeleteReport}
        onCancel={() => setConfirmDeleteOpen(false)}
      />
    </div>
  );
}
