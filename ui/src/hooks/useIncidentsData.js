import { useCallback, useEffect, useRef, useState } from 'react'
import { getIncidents, getUsers } from '../api'

export function useIncidentsData({ visibilityTab = 'public', selectedGroup = '', showHiddenResolved = false, canReadUsers = false } = {}) {
  const [incidents, setIncidents] = useState([])
  const [incidentUsers, setIncidentUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const requestIdRef = useRef(0)
  const mountedRef = useRef(true)

  const loadData = useCallback(async () => {
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    const groupId = visibilityTab === 'group' ? selectedGroup : undefined
    const usersPromise = canReadUsers ? getUsers().catch(() => []) : Promise.resolve([])
    setLoading(true)
    setError(null)

    try {
      if (showHiddenResolved) {
        const [openIncidents, resolvedIncidents, usersData] = await Promise.all([
          getIncidents(undefined, visibilityTab, groupId).catch(() => []),
          getIncidents('resolved', visibilityTab, groupId).catch(() => []),
          usersPromise,
        ])

        if (!mountedRef.current || requestId !== requestIdRef.current) return

        const mergedIncidents = []
        const seenIncidentIds = new Set()
        for (const incident of (openIncidents || [])) {
          if (!incident?.id || seenIncidentIds.has(incident.id)) continue
          seenIncidentIds.add(incident.id)
          mergedIncidents.push(incident)
        }
        for (const incident of (resolvedIncidents || [])) {
          if (!incident?.id || seenIncidentIds.has(incident.id)) continue
          seenIncidentIds.add(incident.id)
          mergedIncidents.push(incident)
        }
        setIncidents(mergedIncidents)
        setIncidentUsers(Array.isArray(usersData) ? usersData : [])
      } else {
        const [incidentsData, usersData] = await Promise.all([
          getIncidents(undefined, visibilityTab, groupId).catch(() => []),
          usersPromise,
        ])

        if (!mountedRef.current || requestId !== requestIdRef.current) return

        setIncidents(Array.isArray(incidentsData) ? incidentsData : [])
        setIncidentUsers(Array.isArray(usersData) ? usersData : [])
      }
    } catch (e) {
      if (!mountedRef.current || requestId !== requestIdRef.current) return
      setError(e.message || String(e))
    } finally {
      if (mountedRef.current && requestId === requestIdRef.current) {
        setLoading(false)
      }
    }
  }, [visibilityTab, selectedGroup, showHiddenResolved, canReadUsers])

  useEffect(() => {
    mountedRef.current = true
    loadData()
    return () => {
      mountedRef.current = false
    }
  }, [loadData])

  return { incidents, incidentUsers, loading, error, refresh: loadData, setIncidents, setIncidentUsers, setError }
}
