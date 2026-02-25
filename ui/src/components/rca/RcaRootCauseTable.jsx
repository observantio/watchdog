import React from 'react'
import PropTypes from 'prop-types'
import { Badge, Card } from '../ui'
import Section from './Section'

function severityVariant(severity) {
  if (severity === 'critical' || severity === 'high') return 'error'
  if (severity === 'medium') return 'warning'
  return 'info'
}

export default function RcaRootCauseTable({ report, compact = false }) {
  const causes = report?.root_causes || []
  const ranked = report?.ranked_causes || []

  const inner = (
    <>
      <h3 className="text-lg text-sre-text font-semibold mb-3">Root Causes</h3>
      {causes.length === 0 ? (
        <p className="text-sm text-sre-text-muted">No root causes identified in this report.</p>
      ) : (
        <div className="space-y-3">
          {causes.map((cause, idx) => {
            let tag = null
            let text = cause.hypothesis || ''
            const m = text.match(/^\[([^\]]+)\]\s*(.*)$/)
            if (m) {
              tag = m[1]
              text = m[2]
            }
            const panel = (
              <Card className='border p-3'>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    {tag && (
                      <span className="text-xs font-mono text-sre-text-muted">[{tag}]</span>
                    )}
                    <p className="text-sm text-sre-text font-medium">{text}</p>
                  </div>
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
              </Card>
            )
            if (compact) {
              return <div key={`${cause.hypothesis}-${idx}`}>{panel}</div>
            }
            return (
              <Card key={`${cause.hypothesis}-${idx}`} className="p-3">
                {panel}
              </Card>
            )
          })}
        </div>
      )}
    </>
  )

  if (compact) {
    return <div>{inner}</div>
  }

  return (
    <Section>{inner}</Section>
  )
}

RcaRootCauseTable.propTypes = {
  report: PropTypes.object,
  compact: PropTypes.bool,
}