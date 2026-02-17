`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import PropTypes from 'prop-types'
import { Input, Textarea } from '../ui'
import HelpTooltip from '../HelpTooltip'

export default function GroupForm({ formData, setFormData }) {
  return (
    <div className="space-y-4 pb-4 border-b border-sre-border">
      <div className="flex items-center gap-2">
        <h3 className="font-semibold text-sre-text">Group Details</h3>
        <HelpTooltip text="Basic information about the group including name and purpose." />
      </div>

      <div className="flex items-start gap-2">
        <div className="flex-1">
          <Input
            label="Group Name *"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder="e.g., SRE Team, DevOps, Security"
            required
            autoFocus
          />
        </div>
        <HelpTooltip text="A unique name for the group. This will be displayed throughout the system." />
      </div>

      <div className="flex items-start gap-2">
        <div className="flex-1">
          <Textarea
            label="Description"
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            placeholder="Describe the group's purpose and responsibilities"
            rows={2}
          />
        </div>
        <HelpTooltip text="An optional description to explain the group's role and responsibilities." />
      </div>
    </div>
  )
}

GroupForm.propTypes = {
  formData: PropTypes.shape({ name: PropTypes.string, description: PropTypes.string }).isRequired,
  setFormData: PropTypes.func.isRequired,
}
