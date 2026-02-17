`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import PropTypes from 'prop-types'
import { Spinner } from '../ui'
import LogVolume from '../loki/LogVolume'
import TraceVolume from '../tempo/TraceVolume'

export function DataVolume({ loadingLogs, logVolumeSeries, loadingTempoVolume, tempoVolumeSeries }) {
  return (
    <div className="space-y-4">
      {loadingLogs ? (
        <div className="flex items-center gap-2 text-sre-text-muted"><Spinner size="sm" /> Loading logs...</div>
      ) : (
        <LogVolume volume={logVolumeSeries} />
      )}

      {loadingTempoVolume ? (
        <div className="flex items-center gap-2 text-sre-text-muted"><Spinner size="sm" /> Loading traces...</div>
      ) : (
        <TraceVolume volume={tempoVolumeSeries} />
      )}
    </div>
  )
}

DataVolume.propTypes = {
  loadingLogs: PropTypes.bool.isRequired,
  logVolumeSeries: PropTypes.array.isRequired,
  loadingTempoVolume: PropTypes.bool.isRequired,
  tempoVolumeSeries: PropTypes.array.isRequired,
}