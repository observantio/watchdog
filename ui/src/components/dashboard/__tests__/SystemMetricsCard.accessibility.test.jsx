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
import { SystemMetricsCard } from '../SystemMetricsCard'

expect.extend(toHaveNoViolations)

describe('SystemMetricsCard accessibility', () => {
  it('renders issues and has no obvious a11y violations', async () => {
    const systemMetrics = {
      stress: { status: 'moderate', message: 'High load', issues: ['disk pressure', 'high gc'] },
      cpu: { utilization: 12.3, threads: 4 },
      memory: { utilization: 45.1, rss_mb: 1024 },
      io: { read_mb: 1.2, write_mb: 3.4 },
      network: { total_connections: 10, established: 6 }
    }

    const { container } = render(<SystemMetricsCard loading={false} systemMetrics={systemMetrics} />)

    expect(screen.getByText(/disk pressure/)).toBeInTheDocument()
    expect(screen.getByText(/high gc/)).toBeInTheDocument()

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})