import React from 'react'
import { fireEvent, render } from '@testing-library/react'
import RCAPage from '../RCAPage'

const createJobMock = vi.fn(async () => ({ job_id: 'job-1', status: 'queued' }))
const refreshJobsMock = vi.fn()
const setSelectedJobIdMock = vi.fn()
const reloadReportMock = vi.fn()

vi.mock('../../hooks/useRcaJobs', () => ({
  useRcaJobs: () => ({
    jobs: [],
    loadingJobs: false,
    creatingJob: false,
    selectedJobId: null,
    selectedJob: null,
    setSelectedJobId: setSelectedJobIdMock,
    createJob: createJobMock,
    refreshJobs: refreshJobsMock,
  }),
}))

vi.mock('../../hooks/useRcaReport', () => ({
  useRcaReport: () => ({
    loadingReport: false,
    reportError: null,
    report: null,
    insights: {},
    hasReport: false,
    reloadReport: reloadReportMock,
  }),
}))

describe('RCAPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('submits a create job request from composer', () => {
    const { getByText } = render(<RCAPage />)
    fireEvent.click(getByText('Generate Report'))
    expect(createJobMock).toHaveBeenCalledTimes(1)
    const payload = createJobMock.mock.calls[0][0]
    expect(payload).toHaveProperty('start')
    expect(payload).toHaveProperty('end')
    expect(payload).toHaveProperty('sensitivity')
  })
})
