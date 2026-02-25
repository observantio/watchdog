`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

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