import PropTypes from 'prop-types'
import { Badge, Button, Card, Spinner } from '../ui'

function statusVariant(status) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'running') return 'warning'
  return 'info'
}

export default function RcaJobQueuePanel({
  jobs,
  loading,
  selectedJobId,
  onSelectJob,
  onRefresh,
}) {
  return (
    <Card className="border border-sre-border p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg text-sre-text font-semibold">RCA Jobs</h3>
        <Button size="sm" variant="secondary" onClick={onRefresh}>Refresh</Button>
      </div>
      {loading ? (
        <div className="py-8 flex justify-center"><Spinner /></div>
      ) : jobs.length === 0 ? (
        <p className="text-sm text-sre-text-muted">No RCA jobs yet.</p>
      ) : (
        <div className="space-y-2 max-h-[320px] overflow-y-auto pr-1">
          {jobs.map((job) => (
            <button
              key={job.job_id}
              type="button"
              onClick={() => onSelectJob(job.job_id)}
              className={`w-full rounded-lg border px-3 py-2 text-left transition ${
                selectedJobId === job.job_id
                  ? 'border-sre-primary bg-sre-primary/10'
                  : 'border-sre-border bg-sre-surface/30 hover:bg-sre-surface/50'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-sre-text font-mono truncate">{job.job_id}</span>
                <Badge variant={statusVariant(job.status)}>{job.status}</Badge>
              </div>
              <p className="text-xs text-sre-text-muted mt-1">
                {job.created_at ? new Date(job.created_at).toLocaleString() : 'pending'}
              </p>
              {job.summary_preview && (
                <p className="text-xs text-sre-text mt-1 line-clamp-2">{job.summary_preview}</p>
              )}
              {job.error && (
                <p className="text-xs text-sre-error mt-1 line-clamp-2">{job.error}</p>
              )}
            </button>
          ))}
        </div>
      )}
    </Card>
  )
}

RcaJobQueuePanel.propTypes = {
  jobs: PropTypes.arrayOf(PropTypes.shape({
    job_id: PropTypes.string.isRequired,
    status: PropTypes.string.isRequired,
    created_at: PropTypes.string,
    summary_preview: PropTypes.string,
    error: PropTypes.string,
  })).isRequired,
  loading: PropTypes.bool,
  selectedJobId: PropTypes.string,
  onSelectJob: PropTypes.func.isRequired,
  onRefresh: PropTypes.func.isRequired,
}
