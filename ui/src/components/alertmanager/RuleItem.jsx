`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { Button } from '../ui'
import { getSeverityVariant } from '../../utils/alertManagerConstants'

const RuleItem = ({ rule, orgIdToName, onTest, onEdit, onDelete }) => {
  const severityVariant = getSeverityVariant(rule.severity)

  return (
    <div
      key={rule.id}
      className="p-6 bg-sre-surface border-2 border-sre-border rounded-xl hover:border-sre-primary/50 hover:shadow-md transition-all duration-200"
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-3">
            <div className={`p-2 rounded-lg ${
              rule.severity === 'critical'
                ? 'bg-red-100 dark:bg-red-900/30'
                : rule.severity === 'warning'
                ? 'bg-yellow-100 dark:bg-yellow-900/30'
                : 'bg-blue-100 dark:bg-blue-900/30'
            }`}>
              <span className={`material-icons text-xl ${
                rule.severity === 'critical'
                  ? 'text-red-600 dark:text-red-400'
                  : rule.severity === 'warning'
                  ? 'text-yellow-600 dark:text-yellow-400'
                  : 'text-blue-600 dark:text-blue-400'
              }`}>
                {severityVariant}
              </span>
            </div>
            <div>
              <h3 className="font-semibold text-sre-text text-lg">{rule.name}</h3>
              <div className="flex items-center gap-2 mt-1">
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                  rule.severity === 'critical'
                    ? 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200'
                    : rule.severity === 'warning'
                    ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-200'
                    : 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200'
                }`}>
                  {rule.severity}
                </span>
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                  rule.enabled
                    ? 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200'
                    : 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200'
                }`}>
                  {rule.enabled ? 'Enabled' : 'Disabled'}
                </span>
                <span className="px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200">
                  {rule.group}
                </span>
                {rule.orgId ? (
                  <span className="px-2 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-200">
                    {orgIdToName[rule.orgId] || `${rule.orgId.slice(0, 8)}...`}
                  </span>
                ) : (
                  <span className="px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200">
                    All products
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="space-y-2 text-sm text-sre-text-muted p-4">
            <div className="flex items-center gap-2">
              <span className="material-icons text-sm">functions</span>
              <span className="font-mono text-xs bg-sre-bg-alt px-2 py-1 rounded border">{rule.expr}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="material-icons text-sm">schedule</span>
              <span>Duration: {rule.duration}</span>
            </div>
            {rule.annotations?.summary && (
              <div className="flex items-start gap-2">
                <span className="material-icons text-sm mt-0.5">description</span>
                <span>{rule.annotations.summary}</span>
              </div>
            )}
          </div>
        </div>

        <div className="flex gap-1 ml-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onTest(rule.id)}
            className="p-2"
            title="Test Rule"
          >
            <span className="material-icons text-base">science</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onEdit(rule)}
            className="p-2"
            title="Edit Rule"
          >
            <span className="material-icons text-base">edit</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onDelete(rule.id)}
            className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-900/20"
            title="Delete Rule"
          >
            <span className="material-icons text-base">delete</span>
          </Button>
        </div>
      </div>
    </div>
  )
}

export default RuleItem