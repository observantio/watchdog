import PropTypes from 'prop-types'
import { Badge, Card } from '../ui'

function severityVariant(severity) {
  if (severity === 'critical' || severity === 'high') return 'error'
  if (severity === 'medium') return 'warning'
  return 'info'
}

export default function RcaRootCauseTable({ report }) {
  const causes = report?.root_causes || []
  const ranked = report?.ranked_causes || []

  return (
    <Card className="border border-sre-border p-4">
      <h3 className="text-lg text-sre-text font-semibold mb-3">Root Causes</h3>
      {causes.length === 0 ? (
        <p className="text-sm text-sre-text-muted">No root causes identified in this report.</p>
      ) : (
        <div className="space-y-3">
          {causes.map((cause, idx) => (
            <div key={`${cause.hypothesis}-${idx}`} className="border border-sre-border rounded-lg p-3 bg-sre-surface/30">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm text-sre-text font-medium">{cause.hypothesis}</p>
                <Badge variant={severityVariant(cause.severity)}>{cause.severity || 'unknown'}</Badge>
              </div>
              <p className="text-xs text-sre-text-muted mt-1">
                Confidence: {typeof cause.confidence === 'number' ? cause.confidence.toFixed(3) : '-'}
              </p>
              {cause.recommended_action && (
                <p className="text-xs text-sre-primary mt-1">Action: {cause.recommended_action}</p>
              )}
              {Array.isArray(cause.evidence) && cause.evidence.length > 0 && (
                <p className="text-xs text-sre-text-muted mt-1">Evidence: {cause.evidence.join(' | ')}</p>
              )}
              {Array.isArray(cause.contributing_signals) && cause.contributing_signals.length > 0 && (
                <p className="text-xs text-sre-text-muted mt-1">Signals: {cause.contributing_signals.join(', ')}</p>
              )}
              {ranked[idx]?.final_score !== undefined && (
                <p className="text-xs text-sre-text-muted mt-1">
                  Rank score: {Number(ranked[idx].final_score).toFixed(3)} (ML {Number(ranked[idx].ml_score || 0).toFixed(3)})
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

RcaRootCauseTable.propTypes = {
  report: PropTypes.object,
}
