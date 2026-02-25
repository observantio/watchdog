import React from 'react'
import { renderHook, waitFor } from '@testing-library/react'
import { vi, describe, it, beforeEach, expect } from 'vitest'

vi.mock('../../api', () => ({
  getIncidents: vi.fn(),
  getUsers: vi.fn(),
}))

import * as api from '../../api'
import { useIncidentsData } from '../useIncidentsData'

describe('useIncidentsData', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads incidents and users (non-hidden)', async () => {
    api.getIncidents.mockResolvedValue([{ id: 'i1' }])
    api.getUsers.mockResolvedValue([{ id: 'u1' }])

    const { result } = renderHook(() => useIncidentsData({ visibilityTab: 'public', showHiddenResolved: false, canReadUsers: true }))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.incidents).toEqual([{ id: 'i1' }])
    expect(result.current.incidentUsers).toEqual([{ id: 'u1' }])
  })

  it('merges resolved + open when showHiddenResolved=true', async () => {
    api.getIncidents.mockImplementation((status) => {
      if (status === 'resolved') return Promise.resolve([{ id: 'r1' }])
      return Promise.resolve([{ id: 'o1' }])
    })
    api.getUsers.mockResolvedValue([])

    const { result } = renderHook(() => useIncidentsData({ showHiddenResolved: true, canReadUsers: false }))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.incidents).toEqual([{ id: 'o1' }, { id: 'r1' }])
  })
})