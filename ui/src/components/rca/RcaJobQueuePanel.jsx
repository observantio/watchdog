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
  onReload,
  onDelete,
  onView,
  deletingReport,
  canDelete,
}) {
  return (
    <Card className="">
      <div className="mb-3">
        <h3 className="text-lg text-sre-text font-semibold">RCA Jobs</h3>
      </div>
      {loading ? (
        <div className="py-8 flex justify-center"><Spinner /></div>
      ) : jobs.length === 0 ? (
        <p className="text-sm text-sre-text-muted">No RCA jobs yet.</p>
      ) : (
        <div className="space-y-2 max-h-[320px] overflow-y-auto pr-1">
          {jobs.map((job) => {
            const isSelected = selectedJobId === job.job_id
            return (
              <div
                key={job.job_id}
                onClick={() => onSelectJob(job.job_id)}
                className={`relative w-full rounded-lg border px-3 py-2 transition cursor-pointer ${
                  isSelected
                    ? 'border-sre-primary bg-sre-primary/10'
                    : 'border-sre-border bg-sre-surface/30 hover:bg-sre-surface/50'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-sre-text font-mono truncate">{job.job_id}</span>
                  {isSelected ? (
                    <div className="flex items-center gap-1 ml-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label="Reload"
                        className="p-1"
                        onClick={(e) => { e.stopPropagation(); onReload && onReload(job); }}
                        title="Reload"
                      >
                        <span className="material-icons text-base">refresh</span>
                      </Button>
                      {onView && (
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label="View"
                          className="p-1"
                          onClick={(e) => { e.stopPropagation(); onView(job); }}
                          title="View"
                        >
                          <span className="material-icons text-base">visibility</span>
                        </Button>
                      )}
                      {canDelete && (
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label="Delete"
                          className="p-1"
                          loading={deletingReport}
                          onClick={(e) => { e.stopPropagation(); onDelete && onDelete(job); }}
                          title="Delete"
                        >
                          <span className="material-icons text-base text-sre-error">delete</span>
                        </Button>
                      )}
                      <Badge variant={statusVariant(job.status)}>{job.status}</Badge>
                    </div>
                  ) : (
                    <Badge variant={statusVariant(job.status)}>{job.status}</Badge>
                  )}
                </div>
                {job.report_id && (
                  <p className="text-xs text-sre-text-muted mt-1 font-mono truncate">report: {job.report_id}</p>
                )}
                <p className="text-xs text-sre-text-muted mt-1">
                  {job.created_at ? new Date(job.created_at).toLocaleString() : 'pending'}
                </p>
                {job.summary_preview && (
                  <p className="text-xs text-sre-text mt-1 line-clamp-2">{job.summary_preview}</p>
                )}
                {job.error && (
                  <p className="text-xs text-sre-error mt-1 line-clamp-2">{job.error}</p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}

RcaJobQueuePanel.propTypes = {
  jobs: PropTypes.arrayOf(PropTypes.shape({
    job_id: PropTypes.string.isRequired,
    report_id: PropTypes.string,
    status: PropTypes.string.isRequired,
    created_at: PropTypes.string,
    summary_preview: PropTypes.string,
    error: PropTypes.string,
  })).isRequired,
  loading: PropTypes.bool,
  selectedJobId: PropTypes.string,
  onSelectJob: PropTypes.func.isRequired,
  onRefresh: PropTypes.func.isRequired,
  onReload: PropTypes.func,
  onDelete: PropTypes.func,
  onView: PropTypes.func,
  deletingReport: PropTypes.bool,
  canDelete: PropTypes.bool,
}
