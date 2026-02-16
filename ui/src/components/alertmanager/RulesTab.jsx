import React from 'react'
import { Button } from '../ui'
import RuleItem from './RuleItem'

const RulesTab = ({ rules, orgIdToName, onImport, onCreate, onTestRule, onEditRule, onDeleteRule }) => {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="material-icons text-2xl text-sre-primary">rule</span>
          <div>
            <h2 className="text-xl font-semibold text-sre-text">Alert Rules</h2>
            <p className="text-sm text-sre-text-muted">
              {rules.length > 0
                ? `${rules.length} rule${rules.length !== 1 ? 's' : ''} configured`
                : 'No rules configured'
              }
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={onImport}
          >
            <span className="material-icons text-sm mr-2">upload_file</span>
            Import YAML
          </Button>
          {rules.length > 0 && (
            <Button onClick={onCreate}>
              <span className="material-icons text-sm mr-2">add</span>
              Create Rule
            </Button>
          )}
        </div>
      </div>

      {rules.length > 0 ? (
        <div className="grid gap-4">
          {rules.map((rule) => (
            <RuleItem
              key={rule.id}
              rule={rule}
              orgIdToName={orgIdToName}
              onTest={onTestRule}
              onEdit={onEditRule}
              onDelete={onDeleteRule}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
          <span className="material-icons text-5xl text-sre-text-muted mb-4 block">rule</span>
          <h3 className="text-xl font-semibold text-sre-text mb-2">No Rules Configured</h3>
          <p className="text-sre-text-muted mb-6 max-w-md mx-auto">
            Create alert rules to monitor your systems and get notified when issues occur.
          </p>
          <Button onClick={onCreate}>
            <span className="material-icons text-sm mr-2">add</span>
            Create Your First Rule
          </Button>
        </div>
      )}
    </div>
  )
}

export default RulesTab