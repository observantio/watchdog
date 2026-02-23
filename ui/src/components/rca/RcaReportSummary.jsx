import PropTypes from 'prop-types'
import { Card, MetricCard } from '../ui'

function severityStatus(severity) {
  if (severity === 'critical' || severity === 'high') return 'error'
  if (severity === 'medium') return 'warning'
  return 'success'
}

export default function RcaReportSummary({ report }) {
  if (!report) return null

  return (
    <Card className="border border-sre-border p-4">
      <h3 className="text-lg text-sre-text font-semibold mb-2">Report Summary</h3>
      <p className="text-sm text-sre-text-muted mb-4">{report.summary || 'No summary available'}</p>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <MetricCard label="Overall Severity" value={String(report.overall_severity || 'unknown').toUpperCase()} status={severityStatus(report.overall_severity)} />
        <MetricCard label="Metric Anomalies" value={report.metric_anomalies?.length || 0} status="info" />
        <MetricCard label="Root Causes" value={report.root_causes?.length || 0} status="warning" />
        <MetricCard label="Duration (s)" value={report.duration_seconds || 0} status="default" />
      </div>
    </Card>
  )
}

RcaReportSummary.propTypes = {
  report: PropTypes.object,
}
