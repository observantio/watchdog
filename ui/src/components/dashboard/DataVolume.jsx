import PropTypes from 'prop-types'
import { Spinner } from '../ui'
import LogVolume from '../loki/LogVolume'

export function DataVolume({ loadingLogs, logVolumeSeries }) {
  return (
    <div className="space-y-4">
      {loadingLogs ? (
        <div className="flex items-center gap-2 text-sre-text-muted"><Spinner size="sm" /> Loading logs...</div>
      ) : (
        <LogVolume volume={logVolumeSeries} />
      )}
    </div>
  )
}

DataVolume.propTypes = {
  loadingLogs: PropTypes.bool.isRequired,
  logVolumeSeries: PropTypes.array.isRequired,
}
