import React from 'react'
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe, toHaveNoViolations } from 'jest-axe'
import AlertsTab from '../AlertsTab'

expect.extend(toHaveNoViolations)

describe('AlertsTab accessibility', () => {
  it('renders alerts and has no a11y violations', async () => {
    const alerts = [
      { id: 'a1', labels: { alertname: 'DiskFull', severity: 'critical' }, annotations: { summary: 'Disk full' }, status: { state: 'active' }, starts_at: new Date().toISOString() },
      { id: 'a2', labels: { alertname: 'CPUSpike', severity: 'warning' }, annotations: { summary: 'CPU spike' }, status: { state: 'active' }, starts_at: new Date().toISOString() }
    ]

    const { container } = render(<AlertsTab filteredAlerts={alerts} filterSeverity={'all'} onFilterChange={() => {}} />)

    expect(screen.getByText('DiskFull')).toBeInTheDocument()
    expect(screen.getByText('CPUSpike')).toBeInTheDocument()

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})