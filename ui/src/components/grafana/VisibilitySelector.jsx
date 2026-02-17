`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { Select, Checkbox } from '../../components/ui'
import { VISIBILITY_OPTIONS } from '../../utils/constants'

export default function VisibilitySelector({
  visibility,
  onVisibilityChange,
  sharedGroupIds,
  onSharedGroupIdsChange,
  groups
}) {
  return (
    <>
      <Select value={visibility} onChange={(e) => onVisibilityChange(e.target.value)}>
        {VISIBILITY_OPTIONS.map(opt => (<option key={opt.value} value={opt.value}>{opt.label}</option>))}
      </Select>
      {visibility === 'group' && (
        <div className="mt-4">
          <label className="block text-sm font-medium text-sre-text mb-2">Shared Groups</label>
          <div className="space-y-2 max-h-40 overflow-y-auto border border-sre-border rounded p-3">
            {groups.map(group => (
              <Checkbox key={group.id} label={group.name} checked={sharedGroupIds.includes(group.id)} onChange={(e) => {
                if (e.target.checked) onSharedGroupIdsChange([...sharedGroupIds, group.id])
                else onSharedGroupIdsChange(sharedGroupIds.filter(id => id !== group.id))
              }} />
            ))}
            {groups.length === 0 && <p className="text-sm text-sre-text-muted">No groups available</p>}
          </div>
        </div>
      )}
    </>
  )
}