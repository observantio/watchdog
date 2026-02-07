import { useState } from 'react'
import PropTypes from 'prop-types'
import { Button, Input, Select } from '../ui'

export default function RuleEditor({ rule, channels, onSave, onCancel }) {
  const [formData, setFormData] = useState(rule || {
    name: '',
    expr: '',
    duration: '1m',
    severity: 'warning',
    labels: {},
    annotations: { summary: '', description: '' },
    enabled: true,
    group: 'default',
    notificationChannels: []
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave(formData)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Input
          label="Rule Name"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          required
          placeholder="e.g., HighCPUUsage"
        />
        <Select
          label="Severity"
          value={formData.severity}
          onChange={(e) => setFormData({ ...formData, severity: e.target.value })}
        >
          <option value="info">Info</option>
          <option value="warning">Warning</option>
          <option value="critical">Critical</option>
        </Select>
      </div>

      <Input
        label="PromQL Expression"
        value={formData.expr}
        onChange={(e) => setFormData({ ...formData, expr: e.target.value })}
        required
        placeholder="e.g., rate(requests_total[5m]) > 100"
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Input
          label="Duration"
          value={formData.duration}
          onChange={(e) => setFormData({ ...formData, duration: e.target.value })}
          placeholder="e.g., 5m, 1h"
        />
        <Input
          label="Group"
          value={formData.group}
          onChange={(e) => setFormData({ ...formData, group: e.target.value })}
          placeholder="default"
        />
      </div>

      <Input
        label="Summary"
        value={formData.annotations.summary}
        onChange={(e) => setFormData({ ...formData, annotations: { ...formData.annotations, summary: e.target.value }})}
        placeholder="Brief alert summary"
      />

      <Input
        label="Description"
        value={formData.annotations.description}
        onChange={(e) => setFormData({ ...formData, annotations: { ...formData.annotations, description: e.target.value }})}
        placeholder="Detailed description"
      />

      <div>
        <label className="block text-sm font-medium text-sre-text mb-2">
          Notification Channels {formData.notificationChannels?.length > 0 ? `(${formData.notificationChannels.length} selected)` : '(All channels)'}
        </label>
        <div className="space-y-2 max-h-48 overflow-y-auto border border-sre-border rounded p-3 bg-sre-surface">
          {channels && channels.length > 0 ? (
            <>
              <div className="flex items-center gap-2 pb-2 border-b border-sre-border">
                <input
                  type="checkbox"
                  id="channel-all"
                  checked={!formData.notificationChannels || formData.notificationChannels.length === 0}
                  onChange={(e) => {
                    let newChannels = []
                    if (!e.target.checked) {
                      newChannels = channels ? channels.map(c => c.id) : []
                    }
                    setFormData({ ...formData, notificationChannels: newChannels })
                  }}
                  className="w-4 h-4"
                />
                <label htmlFor="channel-all" className="text-sm text-sre-text font-medium">
                  All Channels (default)
                </label>
              </div>
              {channels.map((channel) => (
                <div key={channel.id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id={`channel-${channel.id}`}
                    checked={formData.notificationChannels?.includes(channel.id)}
                    onChange={(e) => {
                      const channels = formData.notificationChannels || []
                      const newChannels = e.target.checked
                        ? [...channels, channel.id]
                        : channels.filter(id => id !== channel.id)
                      setFormData({ ...formData, notificationChannels: newChannels })
                    }}
                    className="w-4 h-4"
                  />
                  <label htmlFor={`channel-${channel.id}`} className="text-sm text-sre-text flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-xs ${channel.enabled ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>
                      {channel.type}
                    </span>
                    {channel.name}
                    {!channel.enabled && <span className="text-xs text-gray-500">(disabled)</span>}
                  </label>
                </div>
              ))}
            </>
          ) : (
            <p className="text-sm text-gray-500">No channels configured. Create channels first to assign them to alerts.</p>
          )}
        </div>
        <p className="text-xs text-gray-500 mt-1">
          Select specific channels to notify, or leave empty to notify all channels
        </p>
      </div>

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="enabled"
          checked={formData.enabled}
          onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
          className="w-4 h-4"
        />
        <label htmlFor="enabled" className="text-sm text-sre-text">Enable this rule</label>
      </div>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button type="submit">
          <span className="material-icons text-sm mr-2" aria-hidden="true">save</span>{' '}
          Save Rule
        </Button>
      </div>
    </form>
  )
}

RuleEditor.propTypes = {
  rule: PropTypes.shape({
    name: PropTypes.string,
    expr: PropTypes.string,
    duration: PropTypes.string,
    severity: PropTypes.string,
    labels: PropTypes.object,
    annotations: PropTypes.shape({
      summary: PropTypes.string,
      description: PropTypes.string,
    }),
    enabled: PropTypes.bool,
    group: PropTypes.string,
    notificationChannels: PropTypes.arrayOf(PropTypes.string),
  }),
  channels: PropTypes.arrayOf(PropTypes.object),
  onSave: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
}
