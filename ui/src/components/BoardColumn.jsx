import { Button, Badge, Spinner } from './ui'
import IncidentCard from './IncidentCard'
import HelpTooltip from './HelpTooltip'

export default function BoardColumn({
  title,
  icon,
  color,
  incidents,
  canUpdateIncidents,
  userById,
  dropping,
  handleUnhideIncident,
  openIncidentModal,
  setIncidentModalTab,
  handleDropOnColumn
}) {
  return (
    <div className="flex flex-col">
      <div className="mb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 ${color} rounded-full`}></div>
            <h3 className="text-lg font-semibold text-sre-text">{title}</h3>
            <HelpTooltip text={`Incidents that are ${title.toLowerCase()}.`} />
            <span className="px-2 py-1 bg-sre-surface text-sre-text-muted text-xs font-medium rounded-full border border-sre-border">
              {incidents.length}
            </span>
          </div>
        </div>
        <div className="mt-2 h-1 bg-gradient-to-r from-blue-500 to-blue-400 rounded-full"></div>
      </div>
      <div
        className={`flex-1 min-h-[500px] p-4 rounded-xl border-2 border-dashed border-sre-border/50 bg-sre-surface/30 transition-all duration-200 ${
          canUpdateIncidents ? 'hover:border-sre-primary/30 hover:bg-sre-surface/50 cursor-move' : ''
        }`}
        onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move' }}
        onDrop={(e) => { handleDropOnColumn(title.toLowerCase().replace(' ', ''), e) }}
      >
        <div className="space-y-3">
          {incidents.length > 0 ? (
            incidents.map(incident => (
              <IncidentCard
                key={incident.id}
                incident={incident}
                canUpdateIncidents={canUpdateIncidents}
                userById={userById}
                dropping={dropping}
                handleUnhideIncident={handleUnhideIncident}
                openIncidentModal={openIncidentModal}
                setIncidentModalTab={setIncidentModalTab}
              />
            ))
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <span className="material-icons text-4xl text-sre-text-muted/50 mb-3">{icon}</span>
              <p className="text-sre-text-muted text-sm">No {title.toLowerCase()} incidents</p>
              <p className="text-sre-text-muted/70 text-xs mt-1">Drag incidents here to {title.toLowerCase()}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}