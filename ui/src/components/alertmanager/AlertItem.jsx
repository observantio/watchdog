`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

const AlertItem = ({ alert, idx }) => {
  return (
    <div
      key={alert.fingerprint || alert.id || alert.starts_at || idx}
      className="p-6 bg-sre-surface border-2 border-sre-border rounded-xl hover:border-sre-primary/50 hover:shadow-md transition-all duration-200"
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-3">
            <div className={`p-2 rounded-lg ${
              alert.labels?.severity === 'critical'
                ? 'bg-red-100 dark:bg-red-900/30'
                : 'bg-yellow-100 dark:bg-yellow-900/30'
            }`}>
              <span className={`material-icons text-xl ${
                alert.labels?.severity === 'critical'
                  ? 'text-red-600 dark:text-red-400'
                  : 'text-yellow-600 dark:text-yellow-400'
              }`}>
                {alert.labels?.severity === 'critical' ? 'error' : 'warning'}
              </span>
            </div>
            <div>
              <h3 className="font-semibold text-sre-text text-lg">{alert.labels?.alertname || 'Unknown'}</h3>
              <div className="flex items-center gap-2 mt-1">
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                  alert.labels?.severity === 'critical'
                    ? 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200'
                    : 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-200'
                }`}>
                  {alert.labels?.severity || 'unknown'}
                </span>
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                  alert.status?.state === 'active'
                    ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200'
                    : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'
                }`}>
                  {alert.status?.state || 'active'}
                </span>
              </div>
            </div>
          </div>

          {alert.annotations?.summary && (
            <p className="text-sm text-sre-text-muted mb-3">{alert.annotations.summary}</p>
          )}

          {alert.labels && Object.keys(alert.labels).length > 0 && (
            <div className="flex flex-wrap gap-2">
              {Object.entries(alert.labels)
                .filter(([key]) => !['alertname', 'severity'].includes(key))
                .map(([key, value]) => (
                  <span
                    key={key}
                    className="text-xs px-3 py-1 bg-sre-bg-alt border border-sre-border rounded-full text-sre-text-muted"
                  >
                    {key}={value}
                  </span>
                ))}
            </div>
          )}
        </div>

        <div className="flex flex-col items-end gap-2 ml-4">
          <span className="text-xs text-sre-text-muted whitespace-nowrap">
            {new Date(alert.starts_at || alert.startsAt).toLocaleString()}
          </span>
        </div>
      </div>
    </div>
  )
}

export default AlertItem