`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import PropTypes from 'prop-types'
import { Spinner } from '../ui'

export function SystemMetricsCard({ loading, systemMetrics }) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sre-text-muted text-left">
        <Spinner size="sm" /> Loading metrics...
      </div>
    )
  }

  if (!systemMetrics) {
    return (
      <div className="text-sm text-sre-text-muted text-left">
        Unable to fetch system metrics
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 p-4 rounded-lg border border-sre-border bg-sre-bg-alt">
        <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${
          systemMetrics.stress?.status === 'stressed' ? 'bg-red-500/20 text-red-500' :
          systemMetrics.stress?.status === 'moderate' ? 'bg-yellow-500/20 text-yellow-500' :
          'bg-green-500/20 text-green-500'
        }`}>
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {systemMetrics.stress?.status === 'stressed' ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            )}
          </svg>
        </div>
        <div className="flex-1">
          <div className="font-semibold text-sre-text text-left">
            {systemMetrics.stress?.status === 'stressed' ? 'Server Under Stress' :
             systemMetrics.stress?.status === 'moderate' ? 'Moderate Load' :
             'Server Healthy'}
          </div>
          <div className="text-xs text-sre-text-muted text-left mt-1">
            {systemMetrics.stress?.message}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="p-3 rounded-lg bg-sre-bg-alt border border-sre-border">
          <div className="flex items-center gap-2 mb-2">
            <svg className="w-4 h-4 text-sre-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
            </svg>
            <span className="text-xs font-medium text-sre-text-muted">CPU</span>
          </div>
          <div className="text-lg font-bold text-sre-text">{systemMetrics.cpu?.utilization?.toFixed(1)}%</div>
          <div className="text-xs text-sre-text-muted mt-1">{systemMetrics.cpu?.threads} threads</div>
        </div>

        <div className="p-3 rounded-lg bg-sre-bg-alt border border-sre-border">
          <div className="flex items-center gap-2 mb-2">
            <svg className="w-4 h-4 text-sre-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            <span className="text-xs font-medium text-sre-text-muted">Memory</span>
          </div>
          <div className="text-lg font-bold text-sre-text">{systemMetrics.memory?.utilization?.toFixed(1)}%</div>
          <div className="text-xs text-sre-text-muted mt-1">RSS: {systemMetrics.memory?.rss_mb} MB</div>
        </div>

        <div className="p-3 rounded-lg bg-sre-bg-alt border border-sre-border">
          <div className="flex items-center gap-2 mb-2">
            <svg className="w-4 h-4 text-sre-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
            </svg>
            <span className="text-xs font-medium text-sre-text-muted">I/O</span>
          </div>
          <div className="text-lg font-bold text-sre-text">{(systemMetrics.io?.read_mb + systemMetrics.io?.write_mb)?.toFixed(1)} MB</div>
          <div className="text-xs text-sre-text-muted mt-1">↑{systemMetrics.io?.write_mb} ↓{systemMetrics.io?.read_mb}</div>
        </div>

        <div className="p-3 rounded-lg bg-sre-bg-alt border border-sre-border">
          <div className="flex items-center gap-2 mb-2">
            <svg className="w-4 h-4 text-sre-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
            </svg>
            <span className="text-xs font-medium text-sre-text-muted">Connections</span>
          </div>
          <div className="text-lg font-bold text-sre-text">{systemMetrics.network?.total_connections || 0}</div>
          <div className="text-xs text-sre-text-muted mt-1">{systemMetrics.network?.established || 0} active</div>
        </div>
      </div>

      {systemMetrics.stress?.issues?.length > 0 && (
        <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30">
          <div className="text-xs font-medium text-yellow-600 mb-1">Active Issues</div>
          <ul className="space-y-1">
            {systemMetrics.stress.issues.map((issue) => (
              <li key={issue} className="text-xs text-sre-text-muted">• {issue}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

SystemMetricsCard.propTypes = {
  loading: PropTypes.bool.isRequired,
  systemMetrics: PropTypes.object,
}