`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import PropTypes from 'prop-types'
import Section from './Section'

export default function RcaWarningsPanel({ report, compact = false }) {
  const warnings = report?.analysis_warnings || []
  const changePoints = report?.change_points || []

  const content = (
    <>
      <h3 className="text-lg text-sre-text font-semibold mb-3">Warnings and Change Points</h3>
      {warnings.length === 0 ? (
        <p className="text-sm text-sre-text-muted my-4">No analysis warnings for this report.</p>
      ) : (
        <div className="space-y-1 mb-3">
          {warnings.map((warning, idx) => (
            <p key={idx} className="text-xs text-sre-warning">{warning}</p>
          ))}
        </div>
      )}
      <div>
        <h4 className="text-sm text-sre-text font-semibold mb-2">Change Points ({changePoints.length})</h4>
        {changePoints.length === 0 ? (
          <p className="text-xs text-sre-text-muted">No change points detected.</p>
        ) : (
          <div className="space-y-1 max-h-48 overflow-y-auto border border-sre-border rounded p-2 bg-sre-surface/50">
            {changePoints.slice(0, 30).map((cp, idx) => (
              <p key={idx} className="text-xs text-sre-text-muted">
                {cp.metric_name || cp.metric || 'metric'} at {new Date(Number(cp.timestamp || 0) * 1000).toLocaleString()}
              </p>
            ))}
          </div>
        )}
      </div>
    </>
  )

  if (compact) {
    return <div>{content}</div>
  }

  return <Section>{content}</Section>
}

RcaWarningsPanel.propTypes = {
  report: PropTypes.object,
  compact: PropTypes.bool,
}
