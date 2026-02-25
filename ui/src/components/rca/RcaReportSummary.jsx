import PropTypes from 'prop-types'
import { MetricCard } from '../ui'
import Section from './Section'

function severityStatus(severity) {
  if (severity === 'critical' || severity === 'high') return 'error'
  if (severity === 'medium') return 'warning'
  return 'success'
}

export default function RcaReportSummary({ report, compact = false }) {
  if (!report) return null

  const content = (
    <>
      <h3 className="text-lg text-sre-text font-semibold mb-2">Report Summary</h3>
      <p className="text-sm text-sre-text-muted mb-4">{report.summary || 'No summary available'}</p>
      <div className="flex flex-wrap gap-3">
        <div className="flex-1 min-w-[150px]"><MetricCard label="Overall Severity" value={String(report.overall_severity || 'unknown').toUpperCase()} status={severityStatus(report.overall_severity)} /></div>
        <div className="flex-1 min-w-[150px]"><MetricCard label="Metric Anomalies" value={report.metric_anomalies?.length || 0} status="info" /></div>
        <div className="flex-1 min-w-[150px]"><MetricCard label="Root Causes" value={report.root_causes?.length || 0} status="warning" /></div>
        <div className="flex-1 min-w-[150px]"><MetricCard label="Duration (s)" value={report.duration_seconds || 0} status="default" /></div>
      </div>
    </>
  )

  if (compact) {
    return <div>{content}</div>
  }

  // non-compact, wrap using Section to keep consistent style
  return <Section>{content}</Section>
}

RcaReportSummary.propTypes = {
  report: PropTypes.object,
  compact: PropTypes.bool,
}
