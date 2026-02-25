import React from 'react'
import PropTypes from 'prop-types'
import { Badge, Card } from '../ui'
import Section from './Section'

function severityVariant(severity) {
  if (severity === 'critical' || severity === 'high') return 'error'
  if (severity === 'medium') return 'warning'
  return 'info'
}

function severityOrder(severity) {
  return { critical: 0, high: 1, medium: 2, low: 3 }[severity] ?? 4
}

function ConfidenceBar({ value }) {
  const pct = typeof value === 'number' ? Math.round(value * 100) : null
  if (pct === null) return <span className="text-sre-text-muted">—</span>
  const color = pct >= 80 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-sre-surface rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-sre-text-muted w-8 text-right">{pct}%</span>
    </div>
  )
}

function CauseCard({ cause, rank, index }) {
  let tag = null
  let text = cause.hypothesis || ''
  const m = text.match(/^\[([^\]]+)\]\s*(.*)$/)
  if (m) { tag = m[1]; text = m[2] }

  return (
    <Card className="p-4 flex flex-col gap-3 border border-sre-border">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0">
          <span className="mt-0.5 shrink-0 w-6 h-6 rounded-full bg-sre-surface text-xs font-semibold text-sre-text-muted flex items-center justify-center">
            {index + 1}
          </span>
          <div className="min-w-0">
            {tag && (
              <span className="inline-block text-xs font-mono text-sre-text-muted mb-1">[{tag}]</span>
            )}
            <p className="text-sm font-medium text-sre-text leading-snug">{text}</p>
          </div>
        </div>
        <Badge variant={severityVariant(cause.severity)} className="shrink-0 capitalize">
          {cause.severity || 'unknown'}
        </Badge>
      </div>

      <div className="pl-9 flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs text-sre-text-muted w-20 shrink-0">Confidence</span>
          <div className="flex-1">
            <ConfidenceBar value={cause.confidence} />
          </div>
        </div>

        {rank?.final_score !== undefined && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-sre-text-muted w-20 shrink-0">Rank score</span>
            <span className="text-xs tabular-nums text-sre-text">
              {Number(rank.final_score).toFixed(3)}
              <span className="text-sre-text-muted ml-1">(ML {Number(rank.ml_score || 0).toFixed(3)})</span>
            </span>
          </div>
        )}

        {cause.recommended_action && (
          <div className="flex items-start gap-2">
            <span className="text-xs text-sre-text-muted w-20 shrink-0">Action</span>
            <span className="text-xs text-sre-primary leading-snug">{cause.recommended_action}</span>
          </div>
        )}

        {Array.isArray(cause.evidence) && cause.evidence.length > 0 && (
          <div className="flex items-start gap-2">
            <span className="text-xs text-sre-text-muted w-20 shrink-0">Evidence</span>
            <div className="flex flex-wrap gap-1">
              {cause.evidence.map((e, i) => (
                <span key={i} className="text-xs bg-sre-surface text-sre-text-muted px-2 py-0.5 rounded-md">
                  {e}
                </span>
              ))}
            </div>
          </div>
        )}

        {Array.isArray(cause.contributing_signals) && cause.contributing_signals.length > 0 && (
          <div className="flex items-start gap-2">
            <span className="text-xs text-sre-text-muted w-20 shrink-0">Signals</span>
            <div className="flex flex-wrap gap-1">
              {cause.contributing_signals.map((s, i) => (
                <span key={i} className="text-xs bg-sre-surface text-sre-primary px-2 py-0.5 rounded-md">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}

export default function RcaRootCauseTable({ report, compact = false }) {
  const causes = report?.root_causes || []
  const ranked = report?.ranked_causes || []

  const sorted = [...causes].sort((a, b) => severityOrder(a.severity) - severityOrder(b.severity))

  const inner = (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-sre-text">Root Causes</h3>
        {causes.length > 0 && (
          <span className="text-xs text-sre-text-muted">{causes.length} identified</span>
        )}
      </div>

      {causes.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-10 gap-2 text-sre-text-muted border border-dashed border-sre-border rounded-lg">
          <span className="text-2xl">✓</span>
          <p className="text-sm">No root causes identified</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {sorted.map((cause, idx) => (
            <CauseCard
              key={`${cause.hypothesis}-${idx}`}
              cause={cause}
              rank={ranked[idx]}
              index={idx}
            />
          ))}
        </div>
      )}
    </div>
  )

  if (compact) return <div>{inner}</div>
  return <Section>{inner}</Section>
}

RcaRootCauseTable.propTypes = {
  report: PropTypes.object,
  compact: PropTypes.bool,
}