import { useEffect, useMemo, useState } from 'react'
import PageHeader from '../components/ui/PageHeader'
import { Alert, Button, Card, Spinner } from '../components/ui'
import { useRcaJobs } from '../hooks/useRcaJobs'
import { useRcaReport } from '../hooks/useRcaReport'
import RcaJobComposer from '../components/rca/RcaJobComposer'
import RcaJobQueuePanel from '../components/rca/RcaJobQueuePanel'
import RcaReportSummary from '../components/rca/RcaReportSummary'
import RcaRootCauseTable from '../components/rca/RcaRootCauseTable'
import RcaAnomalyPanels from '../components/rca/RcaAnomalyPanels'
import RcaClusterPanel from '../components/rca/RcaClusterPanel'
import RcaTopologyPanel from '../components/rca/RcaTopologyPanel'
import RcaCausalPanel from '../components/rca/RcaCausalPanel'
import RcaForecastSloPanel from '../components/rca/RcaForecastSloPanel'
import RcaWarningsPanel from '../components/rca/RcaWarningsPanel'

const TAB_STORAGE_KEY = 'rcaPage.activeTab'
const JOB_STORAGE_KEY = 'rcaPage.selectedJobId'

const TABS = [
  { key: 'summary', label: 'Summary' },
  { key: 'root-causes', label: 'Root Causes' },
  { key: 'anomalies', label: 'Anomalies' },
  { key: 'clusters', label: 'Clusters' },
  { key: 'topology', label: 'Topology' },
  { key: 'causal', label: 'Causal' },
  { key: 'forecast-slo', label: 'Forecast/SLO' },
  { key: 'warnings', label: 'Warnings' },
]

export default function RCAPage() {
  const savedTab = (() => {
    try {
      return localStorage.getItem(TAB_STORAGE_KEY) || 'summary'
    } catch {
      return 'summary'
    }
  })()
  const savedJobId = (() => {
    try {
      return localStorage.getItem(JOB_STORAGE_KEY) || null
    } catch {
      return null
    }
  })()

  const [activeTab, setActiveTab] = useState(savedTab)
  const {
    jobs,
    loadingJobs,
    creatingJob,
    selectedJobId,
    selectedJob,
    setSelectedJobId,
    createJob,
    refreshJobs,
  } = useRcaJobs()
  const { loadingReport, reportError, report, insights, hasReport, reloadReport } = useRcaReport(selectedJobId, selectedJob)

  useEffect(() => {
    if (savedJobId && !selectedJobId) {
      setSelectedJobId(savedJobId)
    }
  }, [savedJobId, selectedJobId, setSelectedJobId])

  useEffect(() => {
    try {
      localStorage.setItem(TAB_STORAGE_KEY, activeTab)
    } catch {
      // ignore
    }
  }, [activeTab])

  useEffect(() => {
    if (!selectedJobId) return
    try {
      localStorage.setItem(JOB_STORAGE_KEY, selectedJobId)
    } catch {
      // ignore
    }
  }, [selectedJobId])

  const selectedStatusText = useMemo(() => {
    if (!selectedJob) return 'No job selected'
    return `${selectedJob.status.toUpperCase()}${selectedJob.duration_ms ? ` • ${selectedJob.duration_ms}ms` : ''}`
  }, [selectedJob])

  function renderActiveTab() {
    if (!hasReport) {
      return (
        <Card className="border border-sre-border p-6">
          <p className="text-sm text-sre-text-muted">
            Select a completed RCA job to view report details. Running jobs auto-refresh in the queue.
          </p>
        </Card>
      )
    }
    if (activeTab === 'summary') return <RcaReportSummary report={report} />
    if (activeTab === 'root-causes') return <RcaRootCauseTable report={report} />
    if (activeTab === 'anomalies') return <RcaAnomalyPanels report={report} />
    if (activeTab === 'clusters') return <RcaClusterPanel report={report} />
    if (activeTab === 'topology') return <RcaTopologyPanel topology={insights.topology} />
    if (activeTab === 'causal') {
      return (
        <RcaCausalPanel
          granger={insights.granger}
          bayesian={insights.bayesian}
          mlWeights={insights.mlWeights}
          deployments={insights.deployments}
        />
      )
    }
    if (activeTab === 'forecast-slo') return <RcaForecastSloPanel report={report} forecast={insights.forecast} slo={insights.slo} />
    if (activeTab === 'warnings') return <RcaWarningsPanel report={report} />
    return <RcaReportSummary report={report} />
  }

  return (
    <div className="space-y-4">
      <PageHeader
        icon="psychology"
        title="RCA Console"
        subtitle="Generate and review tenant-scoped root cause analysis reports through Be Observant."
      >
        <Button variant="secondary" onClick={refreshJobs}>Refresh Jobs</Button>
      </PageHeader>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2">
          <RcaJobComposer onCreate={createJob} creating={creatingJob} />
        </div>
        <div className="xl:col-span-1">
          <RcaJobQueuePanel
            jobs={jobs}
            loading={loadingJobs}
            selectedJobId={selectedJobId}
            onSelectJob={setSelectedJobId}
            onRefresh={refreshJobs}
          />
        </div>
      </div>

      <Card className="border border-sre-border p-4">
        <div className="flex flex-wrap items-center gap-2 justify-between">
          <div>
            <p className="text-xs text-sre-text-muted">Selected Job</p>
            <p className="text-sm text-sre-text font-mono">{selectedJobId || '-'}</p>
            <p className="text-xs text-sre-text-muted mt-1">{selectedStatusText}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={reloadReport}>Reload Report</Button>
          </div>
        </div>
      </Card>

      {reportError && <Alert variant="error">{reportError}</Alert>}

      {loadingReport && (
        <Card className="border border-sre-border p-6 flex items-center justify-center">
          <Spinner />
        </Card>
      )}

      <div className="flex flex-wrap gap-2">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={`px-3 py-1.5 rounded-lg text-xs border transition ${
              activeTab === tab.key
                ? 'border-sre-primary bg-sre-primary/10 text-sre-primary'
                : 'border-sre-border text-sre-text-muted hover:text-sre-text hover:bg-sre-surface/40'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {!loadingReport && renderActiveTab()}
    </div>
  )
}
