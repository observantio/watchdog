`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { useEffect, useState } from 'react'
import { fetchHealth, getAlerts, getLogVolume, searchDashboards, getSilences, getDatasources, fetchSystemMetrics, fetchTraceMetrics, getTraceVolume } from '../api'
import { getVolumeValues } from '../utils/lokiQueryUtils'
import { useAuth } from '../contexts/AuthContext'

export function useDashboardData() {
  const { hasPermission } = useAuth()

  // Health state
  const [health, setHealth] = useState(null)
  const [loadingHealth, setLoadingHealth] = useState(true)

  // Alerts state
  const [alertCount, setAlertCount] = useState(null)
  const [loadingAlerts, setLoadingAlerts] = useState(true)

  // Traces state
  const [traceCount, setTraceCount] = useState(null)
  const [traceErrorCount, setTraceErrorCount] = useState(null)
  const [loadingTraces, setLoadingTraces] = useState(true)

  // Logs state
  const [logVolume, setLogVolume] = useState(null)
  const [logVolumeSeries, setLogVolumeSeries] = useState([])
  const [loadingLogs, setLoadingLogs] = useState(true)

  // Tempo volume state
  const [tempoVolumeSeries, setTempoVolumeSeries] = useState([])
  const [loadingTempoVolume, setLoadingTempoVolume] = useState(true)

  // Dashboards state
  const [dashboardCount, setDashboardCount] = useState(null)
  const [loadingDashboards, setLoadingDashboards] = useState(true)

  // Silences state
  const [silenceCount, setSilenceCount] = useState(null)
  const [loadingSilences, setLoadingSilences] = useState(true)

  // Datasources state
  const [datasourceCount, setDatasourceCount] = useState(null)
  const [loadingDatasources, setLoadingDatasources] = useState(true)

  // System metrics state
  const [systemMetrics, setSystemMetrics] = useState(null)
  const [loadingSystemMetrics, setLoadingSystemMetrics] = useState(true)

  const computeLogTotal = (vol) => {
    if (!vol?.data?.result || !Array.isArray(vol.data.result)) return 0
    let total = 0
    for (const series of vol.data.result) {
      if (!Array.isArray(series.values)) continue
      for (const v of series.values) {
        const val = Number(v[1])
        if (!Number.isNaN(val)) total += val
      }
    }
    return total
  }

  useEffect(() => {
    // Fetch health
    ;(async () => {
      try {
        const res = await fetchHealth()
        setHealth(res)
      } catch {
        setHealth(null)
      } finally {
        setLoadingHealth(false)
      }
    })()

    // Fetch alerts
    ;(async () => {
      try {
        setLoadingAlerts(true)
        const data = await getAlerts()
        setAlertCount(Array.isArray(data) ? data.length : 0)
      } catch {
        setAlertCount(0)
      } finally {
        setLoadingAlerts(false)
      }
    })()

    // Fetch traces
    ;(async () => {
      try {
        const endUs = Date.now() * 1000 // ms -> µs
        const startUs = endUs - (60 * 60 * 1000000) // last 1 hour in µs
        const metrics = await fetchTraceMetrics({ start: Math.floor(startUs), end: Math.floor(endUs) })
        setTraceCount(typeof metrics?.total_traces === 'number' ? metrics.total_traces : 0)
        setTraceErrorCount(typeof metrics?.error_count === 'number' ? metrics.error_count : null)
      } catch {
        setTraceCount(0)
        setTraceErrorCount(null)
      } finally {
        setLoadingTraces(false)
      }
    })()

    // Fetch logs
    ;(async () => {
      try {
        const endNs = Date.now() * 1000000 // ms -> ns
        const startNs = endNs - (60 * 60 * 1000000000) // last 1 hour in ns
        const vol = await getLogVolume('{service_name=~".+"}', { start: Math.floor(startNs), end: Math.floor(endNs), step: 60 })
        let total = 0
        try {
          total = computeLogTotal(vol)
        } catch {
          // If computing the total fails, default to 0 so the metric displays "0"
          total = 0
        }
        setLogVolume(total)
        // store series for LogVolume sparkline
        try {
          const series = getVolumeValues(vol)
          setLogVolumeSeries(series)
        } catch (e) {
          setLogVolumeSeries([])
        }
      } catch {
        // On error fetching logs, show 0 instead of leaving the metric as N/A
        setLogVolume(0)
        setLogVolumeSeries([])
      } finally {
        setLoadingLogs(false)
      }
    })()

    // Fetch tempo volume
    ;(async () => {
      try {
        setLoadingTempoVolume(true)
        const endUs = Date.now() * 1000 // ms -> µs
        const startUs = endUs - (60 * 60 * 1000000) // last 1 hour in µs
        const res = await getTraceVolume({ start: Math.floor(startUs), end: Math.floor(endUs), step: 60 })
        try {
          const series = getVolumeValues(res)
          setTempoVolumeSeries(series)
        } catch (e) {
          setTempoVolumeSeries([])
        }
      } catch (e) {
        setTempoVolumeSeries([])
      } finally {
        setLoadingTempoVolume(false)
      }
    })()

    // Fetch dashboards
    ;(async () => {
      if (!hasPermission('read:dashboards')) {
        setLoadingDashboards(false)
        return
      }
      try {
        setLoadingDashboards(true)
        const data = await searchDashboards()
        setDashboardCount(Array.isArray(data) ? data.length : 0)
      } catch {
        setDashboardCount(0)
      } finally {
        setLoadingDashboards(false)
      }
    })()

    // Fetch silences
    ;(async () => {
      if (!hasPermission('read:alerts')) {
        setLoadingSilences(false)
        return
      }
      try {
        setLoadingSilences(true)
        const data = await getSilences()
        setSilenceCount(Array.isArray(data) ? data.length : 0)
      } catch {
        setSilenceCount(0)
      } finally {
        setLoadingSilences(false)
      }
    })()

    // Fetch datasources
    ;(async () => {
      if (!hasPermission('read:dashboards')) {
        setLoadingDatasources(false)
        return
      }
      try {
        setLoadingDatasources(true)
        const data = await getDatasources()
        setDatasourceCount(Array.isArray(data) ? data.length : 0)
      } catch {
        setDatasourceCount(0)
      } finally {
        setLoadingDatasources(false)
      }
    })()

    // Fetch system metrics
    ;(async () => {
      try {
        setLoadingSystemMetrics(true)
        const data = await fetchSystemMetrics()
        setSystemMetrics(data)
      } catch {
        setSystemMetrics(null)
      } finally {
        setLoadingSystemMetrics(false)
      }
    })()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return {
    // Health
    health,
    loadingHealth,

    // Alerts
    alertCount,
    loadingAlerts,

    // Traces
    traceCount,
    traceErrorCount,
    loadingTraces,

    // Logs
    logVolume,
    logVolumeSeries,
    loadingLogs,

    // Tempo volume
    tempoVolumeSeries,
    loadingTempoVolume,

    // Dashboards
    dashboardCount,
    loadingDashboards,

    // Silences
    silenceCount,
    loadingSilences,

    // Datasources
    datasourceCount,
    loadingDatasources,

    // System metrics
    systemMetrics,
    loadingSystemMetrics,
  }
}