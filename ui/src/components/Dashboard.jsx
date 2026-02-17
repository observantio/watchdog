`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { useMemo } from 'react'
import PropTypes from 'prop-types'
import { useDashboardData, useAgentActivity, usePersistentOrder } from '../hooks'
import { getMetricsConfig } from '../constants/dashboard.jsx'
import { MetricsGrid, DashboardLayout } from './dashboard/index.js'
import PageHeader from './ui/PageHeader'

export default function Dashboard({ info }) {
  const dashboardData = useDashboardData()
  const agentData = useAgentActivity()
  const [metricOrder, setMetricOrder] = usePersistentOrder('dashboard-metric-order', 8)
  const metrics = useMemo(() => getMetricsConfig(dashboardData), [dashboardData])
  const handleMetricOrderChange = (newOrder) => {
    setMetricOrder(newOrder)
  }

  return (
    <div className="animate-fade-in">
      <PageHeader
        icon="dashboard"
        title="Observability"
        subtitle="Monitor and manage your observability infrastructure in real-time"
      />

      <MetricsGrid
        metrics={metrics}
        metricOrder={metricOrder}
        onMetricOrderChange={handleMetricOrderChange}
      />

      <DashboardLayout
        dashboardData={dashboardData}
        agentData={agentData}
      />
    </div>
  )
}

Dashboard.propTypes = {
  info: PropTypes.shape({
    service: PropTypes.string,
    version: PropTypes.string,
  }),
}
