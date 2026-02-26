import { useMemo } from 'react'
import { useDashboardData, useAgentActivity, usePersistentOrder } from '../hooks'
import { getMetricsConfig } from '../constants/dashboard.jsx'
import { MetricsGrid, DashboardLayout } from './dashboard/index.js'
import PageHeader from './ui/PageHeader'

export default function Dashboard() {
  const dashboardData = useDashboardData()
  const agentData = useAgentActivity()
  const metrics = useMemo(() => getMetricsConfig(dashboardData), [dashboardData])
  const [metricOrder, setMetricOrder] = usePersistentOrder('dashboard-metric-order', metrics.length)
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
