import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getRcaJobResult,
  fetchRcaBayesian,
  fetchRcaCorrelate,
  fetchRcaForecast,
  fetchRcaGranger,
  fetchRcaSloBurn,
  fetchRcaTopology,
  getRcaDeployments,
  getRcaMlWeights,
} from '../api'

function deriveRootService(report) {
  if (Array.isArray(report?.service_latency) && report.service_latency.length > 0) {
    return report.service_latency[0].service
  }
  if (Array.isArray(report?.error_propagation) && report.error_propagation.length > 0) {
    return report.error_propagation[0].source_service
  }
  return ''
}

function basePayloadFromReport(report) {
  return {
    start: report?.start,
    end: report?.end,
    step: '15s',
    services: Array.from(new Set((report?.service_latency || []).map((s) => s.service).filter(Boolean))).slice(0, 5),
    metric_queries: [],
    log_query: null,
  }
}

export function useRcaReport(selectedJobId, selectedJob) {
  const [loadingReport, setLoadingReport] = useState(false)
  const [reportError, setReportError] = useState(null)
  const [report, setReport] = useState(null)
  const [insights, setInsights] = useState({
    correlate: null,
    topology: null,
    slo: null,
    forecast: null,
    granger: null,
    bayesian: null,
    mlWeights: null,
    deployments: null,
  })

  const loadRelatedInsights = useCallback(async (reportData) => {
    if (!reportData?.start || !reportData?.end) return
    const basePayload = basePayloadFromReport(reportData)
    const rootService = deriveRootService(reportData)

    const calls = [
      fetchRcaCorrelate(basePayload),
      fetchRcaForecast(basePayload),
      fetchRcaGranger(basePayload),
      fetchRcaBayesian({
        ...basePayload,
        apdex_threshold_ms: 500,
        slo_target: 0.999,
        correlation_window_seconds: 60,
        forecast_horizon_seconds: 1800,
      }),
      getRcaMlWeights(),
      getRcaDeployments(),
    ]
    if (rootService) {
      calls.push(fetchRcaTopology({
        start: reportData.start,
        end: reportData.end,
        root_service: rootService,
        max_depth: 6,
      }))
      calls.push(fetchRcaSloBurn({
        service: rootService,
        start: reportData.start,
        end: reportData.end,
        step: '15s',
        target_availability: 0.999,
      }))
    } else {
      calls.push(Promise.resolve(null))
      calls.push(Promise.resolve(null))
    }

    const settled = await Promise.allSettled(calls)
    const [
      correlateRes,
      forecastRes,
      grangerRes,
      bayesianRes,
      mlWeightsRes,
      deploymentsRes,
      topologyRes,
      sloRes,
    ] = settled

    setInsights({
      correlate: correlateRes.status === 'fulfilled' ? correlateRes.value : null,
      forecast: forecastRes.status === 'fulfilled' ? forecastRes.value : null,
      granger: grangerRes.status === 'fulfilled' ? grangerRes.value : null,
      bayesian: bayesianRes.status === 'fulfilled' ? bayesianRes.value : null,
      mlWeights: mlWeightsRes.status === 'fulfilled' ? mlWeightsRes.value : null,
      deployments: deploymentsRes.status === 'fulfilled' ? deploymentsRes.value : null,
      topology: topologyRes.status === 'fulfilled' ? topologyRes.value : null,
      slo: sloRes.status === 'fulfilled' ? sloRes.value : null,
    })
  }, [])

  const loadReport = useCallback(async () => {
    if (!selectedJobId || selectedJobId.startsWith('pending-')) {
      setReport(null)
      setInsights({
        correlate: null,
        topology: null,
        slo: null,
        forecast: null,
        granger: null,
        bayesian: null,
        mlWeights: null,
        deployments: null,
      })
      return
    }
    setLoadingReport(true)
    setReportError(null)
    try {
      const res = await getRcaJobResult(selectedJobId)
      if (res?.status !== 'completed' || !res?.result) {
        setReport(null)
        return
      }
      setReport(res.result)
      await loadRelatedInsights(res.result)
    } catch (err) {
      setReportError(err?.message || 'Failed to load RCA report')
      setReport(null)
    } finally {
      setLoadingReport(false)
    }
  }, [loadRelatedInsights, selectedJobId])

  useEffect(() => {
    if (!selectedJobId) return
    if (selectedJob?.status === 'completed') {
      loadReport()
    } else if (selectedJob?.status === 'failed') {
      setReport(null)
      setReportError(selectedJob?.error || 'RCA job failed')
    } else if (selectedJob?.status === 'queued' || selectedJob?.status === 'running') {
      setReport(null)
      setReportError(null)
    }
  }, [loadReport, selectedJob, selectedJobId])

  const hasReport = useMemo(() => Boolean(report), [report])

  return {
    loadingReport,
    reportError,
    report,
    insights,
    hasReport,
    reloadReport: loadReport,
  }
}
