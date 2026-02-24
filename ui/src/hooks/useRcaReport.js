import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  getRcaReportById,
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

const EMPTY_INSIGHTS = {
  correlate: null,
  topology: null,
  slo: null,
  forecast: null,
  granger: null,
  bayesian: null,
  mlWeights: null,
  deployments: null,
}

const EMPTY_INSIGHT_ERRORS = {
  correlate: null,
  topology: null,
  slo: null,
  forecast: null,
  granger: null,
  bayesian: null,
  mlWeights: null,
  deployments: null,
}

export function useRcaReport(selectedJobId, selectedJob, reportIdOverride = null) {
  const requestSeq = useRef(0)
  const [loadingPrimaryReport, setLoadingPrimaryReport] = useState(false)
  const [loadingInsights, setLoadingInsights] = useState(false)
  const [reportError, setReportError] = useState(null)
  // track HTTP status for convenience (e.g. 404 not found)
  const [reportErrorStatus, setReportErrorStatus] = useState(null)
  const [report, setReport] = useState(null)
  const [reportMeta, setReportMeta] = useState(null)
  const [insights, setInsights] = useState(EMPTY_INSIGHTS)
  const [insightErrors, setInsightErrors] = useState(EMPTY_INSIGHT_ERRORS)

  const loadRelatedInsights = useCallback(async (reportData, seq) => {
    if (!reportData?.start || !reportData?.end) return
    setLoadingInsights(true)
    setInsightErrors(EMPTY_INSIGHT_ERRORS)
    const basePayload = basePayloadFromReport(reportData)
    const rootService = deriveRootService(reportData)

    const calls = [
      fetchRcaCorrelate(basePayload),
      fetchRcaForecast(basePayload, { limit: 100 }),
      fetchRcaGranger(basePayload, { limit: 100, min_strength: 0.05, max_series: 25 }),
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
    if (seq !== requestSeq.current) return

    const [correlateRes, forecastRes, grangerRes, bayesianRes, mlWeightsRes, deploymentsRes, topologyRes, sloRes] = settled
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
    setInsightErrors({
      correlate: correlateRes.status === 'rejected' ? (correlateRes.reason?.message || 'Failed to load correlate insights') : null,
      forecast: forecastRes.status === 'rejected' ? (forecastRes.reason?.message || 'Failed to load forecast insights') : null,
      granger: grangerRes.status === 'rejected' ? (grangerRes.reason?.message || 'Failed to load causal insights') : null,
      bayesian: bayesianRes.status === 'rejected' ? (bayesianRes.reason?.message || 'Failed to load bayesian insights') : null,
      mlWeights: mlWeightsRes.status === 'rejected' ? (mlWeightsRes.reason?.message || 'Failed to load weights') : null,
      deployments: deploymentsRes.status === 'rejected' ? (deploymentsRes.reason?.message || 'Failed to load deployments') : null,
      topology: topologyRes.status === 'rejected' ? (topologyRes.reason?.message || 'Failed to load topology') : null,
      slo: sloRes.status === 'rejected' ? (sloRes.reason?.message || 'Failed to load SLO') : null,
    })
    setLoadingInsights(false)
  }, [])

  const reset = useCallback(() => {
    setReport(null)
    setReportMeta(null)
    setInsights(EMPTY_INSIGHTS)
    setInsightErrors(EMPTY_INSIGHT_ERRORS)
    setLoadingInsights(false)
  }, [])

  const loadReport = useCallback(async () => {
    const seq = requestSeq.current + 1
    requestSeq.current = seq

    if (!reportIdOverride && (!selectedJobId || selectedJobId.startsWith('pending-'))) {
      reset()
      setReportError(null)
      setLoadingPrimaryReport(false)
      return
    }

    setLoadingPrimaryReport(true)
    setReportError(null)
    try {
      const res = reportIdOverride
        ? await getRcaReportById(reportIdOverride)
        : await getRcaJobResult(selectedJobId)
      if (seq !== requestSeq.current) return

      setReportMeta({
        job_id: res?.job_id,
        report_id: res?.report_id,
        status: res?.status,
        tenant_id: res?.tenant_id,
        requested_by: res?.requested_by,
      })
      if (res?.status !== 'completed' || !res?.result) {
        setReport(null)
        setInsights(EMPTY_INSIGHTS)
        setInsightErrors(EMPTY_INSIGHT_ERRORS)
        setLoadingInsights(false)
      } else {
        setReport(res.result)
        setLoadingPrimaryReport(false)
        void loadRelatedInsights(res.result, seq)
        return
      }
    } catch (err) {
      if (seq !== requestSeq.current) return
      setReportError(err?.message || 'Failed to load RCA report')
      setReportErrorStatus(err?.status || null)
      reset()
    } finally {
      if (seq === requestSeq.current) {
        setLoadingPrimaryReport(false)
      }
    }
  }, [loadRelatedInsights, reportIdOverride, reset, selectedJobId])

  useEffect(() => {
    if (reportIdOverride) {
      loadReport()
      return
    }

    if (!selectedJobId) return
    if (selectedJob?.status === 'completed') {
      loadReport()
    } else if (selectedJob?.status === 'failed') {
      requestSeq.current += 1
      reset()
      setReportError(selectedJob?.error || 'RCA job failed')
    } else if (selectedJob?.status === 'queued' || selectedJob?.status === 'running') {
      requestSeq.current += 1
      reset()
      setReportError(null)
    }
  }, [loadReport, reportIdOverride, reset, selectedJob, selectedJobId])

  const hasReport = useMemo(() => Boolean(report), [report])

  return {
    loadingPrimaryReport,
    loadingInsights,
    loadingReport: loadingPrimaryReport || loadingInsights,
    reportError,
    reportErrorStatus,
    report,
    reportMeta,
    insights,
    insightErrors,
    hasReport,
    reloadReport: loadReport,
  }
}
