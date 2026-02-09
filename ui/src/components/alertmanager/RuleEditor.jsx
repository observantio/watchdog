import { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import { Button, Input, Select } from '../ui'
import { getGroups } from '../../api'

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
    notificationChannels: [],
    visibility: 'private',
    sharedGroupIds: []
  })
  const [groups, setGroups] = useState([])
  const [selectedGroups, setSelectedGroups] = useState(new Set(rule?.sharedGroupIds || []))

  useEffect(() => {
    loadGroups()
  }, [])

  const loadGroups = async () => {
    try {
      const groupsData = await getGroups()
      setGroups(groupsData)
    } catch (error) {
      console.error('Error loading groups:', error)
    }
  }

  const toggleGroup = (groupId) => {
    const newGroups = new Set(selectedGroups)
    if (newGroups.has(groupId)) {
      newGroups.delete(groupId)
    } else {
      newGroups.add(groupId)
    }
    setSelectedGroups(newGroups)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave({
      ...formData,
      sharedGroupIds: Array.from(selectedGroups)
    })
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
          {channels?.length > 0 ? (
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

      {/* Visibility Settings */}
      <div className="border-t border-sre-border pt-4 space-y-3">
        <div>
          <label htmlFor="rule-visibility" className="block text-sm font-semibold text-sre-text mb-2">
            <span className="material-icons text-sm align-middle mr-1">visibility</span> Visibility
          </label>
          <Select
            id="rule-visibility"
            value={formData.visibility || 'private'}
            onChange={(e) => {
              const newVisibility = e.target.value
              setFormData({ ...formData, visibility: newVisibility })
              if (newVisibility !== 'group') {
                setSelectedGroups(new Set())
              }
            }}
          >
            <option value="private">Private - Only visible to me</option>
            <option value="group">Group - Share with specific groups</option>
            <option value="tenant">Tenant - Visible to all users in tenant</option>
          </Select>
          <p className="text-xs text-sre-text-muted mt-1">
            {formData.visibility === 'private' && 'Only you can view and edit this rule'}
            {formData.visibility === 'group' && 'Users in selected groups can view this rule'}
            {formData.visibility === 'tenant' && 'All users in your organization can view this rule'}
          </p>
        </div>

        {/* Group Sharing - only show when visibility is 'group' */}
        {formData.visibility === 'group' && groups?.length > 0 && (
          <div>
            <label htmlFor="rule-groups" className="block text-sm font-medium text-sre-text mb-2">
              Share with Groups
            </label>
            <div id="rule-groups" className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-48 overflow-y-auto p-2 border border-sre-border rounded bg-sre-surface">
              {groups.map((group) => (
                <label
                  key={group.id}
                  className="flex items-center gap-2 p-2 bg-sre-bg-alt rounded cursor-pointer hover:bg-sre-accent/10 transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={selectedGroups.has(group.id)}
                    onChange={() => toggleGroup(group.id)}
                    className="w-4 h-4"
                  />
                  <div className="flex-1 text-sm">
                    <div className="font-medium text-sre-text">{group.name}</div>
                    {group.description && (
                      <div className="text-xs text-sre-text-muted truncate">{group.description}</div>
                    )}
                  </div>
                </label>
              ))}
            </div>
            <p className="text-xs text-sre-text-muted mt-2">
              {selectedGroups.size} group{selectedGroups.size === 1 ? '' : 's'} selected
            </p>
          </div>
        )}
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
    sharedGroupIds: PropTypes.arrayOf(PropTypes.string),
  }),
  channels: PropTypes.arrayOf(PropTypes.object),
  onSave: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
}
