import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import LogResults from '../LogResults'

function makeStream(i) {
  // use a valid numeric nanoseconds timestamp string
  const tsNs = String(Date.now() * 1e6 + i)
  return { stream: { service: `svc_${i}` }, values: [[tsNs, `log entry ${i}`]] }
}

describe('LogResults pagination', () => {
  it('paginates streams when streamsPerPage is lower than total', () => {
    const streams = Array.from({ length: 65 }, (_, i) => makeStream(i + 1))
    const queryResult = { data: { result: streams } }

    render(
      <LogResults
        queryResult={queryResult}
        loading={false}
        searchText={''}
        viewMode="table"
        expandedLogs={{}}
        toggleLogExpand={() => {}}
        copyToClipboard={() => {}}
        streamsPerPage={30}
      />
    )

    // initial page shows 1-30
    expect(screen.getByText(/Showing 1–30 of 65 streams/)).toBeInTheDocument()
    expect(screen.getByText('svc_1')).toBeInTheDocument()
    expect(screen.getByText('svc_30')).toBeInTheDocument()
    expect(screen.queryByText('svc_31')).not.toBeInTheDocument()

    // page forward
    fireEvent.click(screen.getByRole('button', { name: /Next/i }))
    expect(screen.getByText(/Showing 31–60 of 65 streams/)).toBeInTheDocument()
    expect(screen.getByText('svc_31')).toBeInTheDocument()
    expect(screen.getByText('svc_60')).toBeInTheDocument()
    expect(screen.queryByText('svc_61')).not.toBeInTheDocument()

    // final page
    fireEvent.click(screen.getByRole('button', { name: /Next/i }))
    expect(screen.getByText(/Showing 61–65 of 65 streams/)).toBeInTheDocument()
    expect(screen.getByText('svc_61')).toBeInTheDocument()
    expect(screen.getByText('svc_65')).toBeInTheDocument()
  })
})