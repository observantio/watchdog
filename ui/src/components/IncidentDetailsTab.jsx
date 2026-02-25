import { Card, Select } from './ui'

export default function IncidentDetailsTab({ activeIncident, activeIncidentDraft, setIncidentDrafts }) {
  return (
    <Card className="p-4">
      <h4 className="text-sm font-semibold text-sre-text text-left mb-3 flex items-center">
        <span className="material-icons text-base mr-2">info</span>
        Incident Details
      </h4>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">Status</label>
          <Select
            value={activeIncidentDraft.status ?? activeIncident.status}
            onChange={(e) => setIncidentDrafts((prev) => ({
              ...prev,
              [activeIncident.id]: { ...(prev[activeIncident.id] || {}), status: e.target.value }
            }))}
          >
            <option value="open">Open</option>
            <option value="resolved">Resolved</option>
          </Select>
        </div>

        <div>
          <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">Visibility</label>
          <div className="p-2 border border-sre-border rounded bg-sre-bg-alt">
            <div className="text-sm text-sre-text">
              {activeIncident.visibility}
              {Array.isArray(activeIncident.sharedGroupIds) && activeIncident.sharedGroupIds.length > 0 && (
                <span className="text-sre-text-muted ml-2 truncate">({activeIncident.sharedGroupIds.join(', ')})</span>
              )}
            </div>
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">Behavior</label>
          <div className="p-2 border border-sre-border rounded bg-sre-bg-alt flex items-center justify-between gap-4">
            <div className="text-sm text-sre-text">Hide when resolved</div>
            <div>
              <label className="inline-flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={activeIncidentDraft.hideWhenResolved ?? activeIncident.hideWhenResolved ?? false}
                  onChange={(e) => setIncidentDrafts((prev) => ({
                    ...prev,
                    [activeIncident.id]: { ...(prev[activeIncident.id] || {}), hideWhenResolved: e.target.checked }
                  }))}
                  className="form-checkbox h-4 w-4 text-sre-primary"
                />
              </label>
            </div>
          </div>
        </div>
      </div>
    </Card>
  )
}