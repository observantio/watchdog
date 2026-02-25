import { useMemo } from 'react'
import PropTypes from 'prop-types'
import { useDashboardData, useAgentActivity, usePersistentOrder } from '../hooks'
import { getMetricsConfig } from '../constants/dashboard.jsx'
import { MetricsGrid, DashboardLayout } from './dashboard/index.js'
import PageHeader from './ui/PageHeader'

export default function Dashboard() {
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


