import { useCallback, useEffect, useMemo, useState } from 'react'
import { createRcaAnalyzeJob, deleteRcaReport, listRcaJobs } from '../api'
import { useToast } from '../contexts/ToastContext'

const JOB_POLL_MS = 5000

function hasActiveJobs(items) {
  return (items || []).some((job) => job.status === 'queued' || job.status === 'running')
}

export function useRcaJobs() {
  const toast = useToast()
  const [jobs, setJobs] = useState([])
  const [loadingJobs, setLoadingJobs] = useState(false)
  const [creatingJob, setCreatingJob] = useState(false)
  const [deletingReport, setDeletingReport] = useState(false)
  const [selectedJobId, setSelectedJobId] = useState(null)

  const refreshJobs = useCallback(async () => {
    setLoadingJobs(true)
    try {
      const res = await listRcaJobs({ limit: 30 })
      const items = Array.isArray(res?.items) ? res.items : []
      setJobs(items)
      if (items.length > 0 && (!selectedJobId || !items.some((job) => job.job_id === selectedJobId))) {
        setSelectedJobId(items[0].job_id)
      }
    } catch (err) {
      toast?.error?.(err?.message || 'Failed to load RCA jobs')
    } finally {
      setLoadingJobs(false)
    }
  }, [selectedJobId, toast])

  useEffect(() => {
    refreshJobs()
  }, [refreshJobs])

  useEffect(() => {
    if (!hasActiveJobs(jobs)) return undefined
    const poll = () => {
      if (typeof document !== 'undefined' && document.hidden) return
      refreshJobs()
    }
    const timer = setInterval(() => {
      poll()
    }, JOB_POLL_MS)
    const onVisibilityChange = () => {
      if (typeof document !== 'undefined' && !document.hidden) {
        poll()
      }
    }
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibilityChange)
    }
    return () => {
      clearInterval(timer)
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisibilityChange)
      }
    }
  }, [jobs, refreshJobs])

  const createJob = useCallback(async (payload) => {
    setCreatingJob(true)
    const optimisticId = `pending-${Date.now()}`
    const optimistic = {
      job_id: optimisticId,
      report_id: `pending-report-${Date.now()}`,
      status: 'queued',
      created_at: new Date().toISOString(),
      started_at: null,
      finished_at: null,
      duration_ms: null,
      error: null,
      summary_preview: 'Submitting RCA analysis request...',
      requested_by: 'me',
      tenant_id: 'current',
    }
    setJobs((prev) => [optimistic, ...prev].slice(0, 30))
    setSelectedJobId(optimisticId)

    try {
      const created = await createRcaAnalyzeJob(payload)
      setJobs((prev) => {
        const withoutOptimistic = prev.filter((job) => job.job_id !== optimisticId)
        return [created, ...withoutOptimistic].slice(0, 30)
      })
      setSelectedJobId(created.job_id)
      toast?.success?.('RCA analysis job created')
      return created
    } catch (err) {
      setJobs((prev) => prev.filter((job) => job.job_id !== optimisticId))
      toast?.error?.(err?.message || 'Failed to create RCA job')
      throw err
    } finally {
      setCreatingJob(false)
    }
  }, [toast])

  const removeJobByReportId = useCallback((reportId) => {
    setJobs((prev) => {
      const next = prev.filter((job) => job.report_id !== reportId)
      if (selectedJobId && !next.some((job) => job.job_id === selectedJobId)) {
        setSelectedJobId(next[0]?.job_id || null)
      }
      return next
    })
  }, [selectedJobId])

  const deleteReportById = useCallback(async (reportId) => {
    setDeletingReport(true)
    try {
      await deleteRcaReport(reportId)
      removeJobByReportId(reportId)
      toast?.success?.('RCA report deleted')
    } catch (err) {
      toast?.error?.(err?.message || 'Failed to delete RCA report')
      throw err
    } finally {
      setDeletingReport(false)
    }
  }, [removeJobByReportId, toast])

  const selectedJob = useMemo(
    () => jobs.find((job) => job.job_id === selectedJobId) || null,
    [jobs, selectedJobId]
  )

  return {
    jobs,
    loadingJobs,
    creatingJob,
    deletingReport,
    selectedJobId,
    selectedJob,
    setSelectedJobId,
    createJob,
    deleteReportById,
    removeJobByReportId,
    refreshJobs,
  }
}
