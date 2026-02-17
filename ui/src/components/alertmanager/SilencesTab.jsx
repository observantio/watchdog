`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { Button } from '../ui'
import SilenceItem from './SilenceItem'

const SilencesTab = ({ silences, onCreate, onDeleteSilence }) => {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="material-icons text-2xl text-sre-primary">volume_off</span>
          <div>
            <h2 className="text-xl font-semibold text-sre-text">Active Silences</h2>
            <p className="text-sm text-sre-text-muted">
              {silences.length > 0
                ? `${silences.length} silence${silences.length !== 1 ? 's' : ''} active`
                : 'No active silences'
              }
            </p>
          </div>
        </div>
        {silences.length > 0 && (
          <Button onClick={onCreate}>
            <span className="material-icons text-sm mr-2">add</span>
            Create Silence
          </Button>
        )}
      </div>

      {silences.length > 0 ? (
        <div className="space-y-4">
          {silences.map((silence) => (
            <SilenceItem
              key={silence.id}
              silence={silence}
              onDelete={onDeleteSilence}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
          <span className="material-icons text-5xl text-sre-text-muted mb-4 block">volume_up</span>
          <h3 className="text-xl font-semibold text-sre-text mb-2">No Active Silences</h3>
          <p className="text-sre-text-muted mb-6 max-w-md mx-auto">
            Silences temporarily suppress alert notifications. Create a silence to stop alerts during maintenance.
          </p>
          <Button onClick={onCreate}>
            <span className="material-icons text-sm mr-2">add</span>
            Create Silence
          </Button>
        </div>
      )}
    </div>
  )
}

export default SilencesTab