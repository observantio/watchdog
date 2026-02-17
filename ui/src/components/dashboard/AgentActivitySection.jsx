`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import PropTypes from 'prop-types'
import { Badge, Spinner } from '../ui'

const AgentStatusBadges = ({ agent }) => (
  <div className="flex flex-wrap items-center justify-end gap-2">
    {agent.is_enabled && <Badge variant="warning">Focused</Badge>}
    <Badge
      variant={agent.active ? "success" : "default"}
      className={agent.active ? "animate-pulse" : ""}
    >
      {agent.active ? "Active" : "Idle"}
    </Badge>
  </div>
)

AgentStatusBadges.propTypes = {
  agent: PropTypes.shape({
    is_enabled: PropTypes.bool,
    active: PropTypes.bool,
    clean: PropTypes.bool,
  }).isRequired,
}

const formatActivityLabel = (agent) => {
  const parts = [
    agent.metrics_count > 0 && `Metrics: ${agent.metrics_count}`
  ].filter(Boolean)

  return parts.length > 0 ? parts.join(' · ') : 'No activity'
}

const AgentCard = ({ agent }) => {
  const hostLabel = agent.host_names?.length > 0
    ? agent.host_names.join(', ')
    : null
  const activityLabel = formatActivityLabel(agent)

  const displayName = agent?.name && agent.name.length > 5
    ? agent.name.slice(0, 5) + '...'
    : agent?.name

  return (
    <div className="rounded-lg border border-sre-border bg-sre-bg-alt px-4 py-3">
      <div className="flex items-center gap-4">
        <div className="flex-1">
          <div className="font-semibold text-sre-text text-left">{displayName}</div>
          <div className="text-xs text-sre-text-muted text-left">{activityLabel}</div>
          {hostLabel && (
            <div className="text-xs text-sre-text-muted text-left">Host: {hostLabel}</div>
          )}
        </div>
        <AgentStatusBadges agent={agent} />
      </div>
    </div>
  )
}

AgentCard.propTypes = {
  agent: PropTypes.shape({
    name: PropTypes.string.isRequired,
    host_names: PropTypes.arrayOf(PropTypes.string),
    metrics_count: PropTypes.number,
    is_enabled: PropTypes.bool,
    active: PropTypes.bool,
    clean: PropTypes.bool,
  }).isRequired,
}

const AgentActivityContent = ({ loading, agents }) => {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sre-text-muted text-left">
        <Spinner size="sm" /> Loading activity
      </div>
    )
  }

  if (agents.length === 0) {
    return (
      <div className="text-sm text-sre-text-muted text-left">
        No agent activity detected.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {agents.map((agent) => (
        <AgentCard key={agent.name} agent={agent} />
      ))}
    </div>
  )
}

AgentActivityContent.propTypes = {
  loading: PropTypes.bool.isRequired,
  agents: PropTypes.array.isRequired,
}

export function AgentActivitySection({ loading, agents }) {
  return (
    <AgentActivityContent loading={loading} agents={agents} />
  )
}