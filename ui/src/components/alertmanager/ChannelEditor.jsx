import { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import { Button, Input, Select } from '../ui'
import { getGroups } from '../../api'

/**
 * ChannelEditor component with group/user scoping
 * @param {object} props - Component props
 */
export default function ChannelEditor({ channel, onSave, onCancel }) {
  const [formData, setFormData] = useState(channel || {
    name: '',
    type: 'webhook',
    enabled: true,
    config: {},
    visibility: 'private',
    sharedGroupIds: []
  })
  const [groups, setGroups] = useState([])
  const [selectedGroups, setSelectedGroups] = useState(new Set(channel?.sharedGroupIds || []))

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

  const renderConfigFields = () => {
    switch (formData.type) {
      case 'email':
        return (
          <>
            <Input
              label="Email Address"
              type="email"
              value={formData.config.to || ''}
              onChange={(e) => setFormData({ ...formData, config: { ...formData.config, to: e.target.value }})}
              placeholder="alerts@example.com"
              required
            />
            <Input
              label="SMTP Server"
              value={formData.config.smtpHost || formData.config.smtp_host || ''}
              onChange={(e) => setFormData({
                ...formData,
                config: { ...formData.config, smtpHost: e.target.value, smtp_host: e.target.value }
              })}
              placeholder="smtp.example.com"
            />
            <Input
              label="SMTP Port"
              type="number"
              value={formData.config.smtpPort || formData.config.smtp_port || 587}
              onChange={(e) => setFormData({
                ...formData,
                config: { ...formData.config, smtpPort: Number(e.target.value), smtp_port: Number(e.target.value) }
              })}
            />
          </>
        )
      case 'slack':
        return (
          <>
            <Input
              label="Webhook URL"
              value={formData.config.webhookUrl || formData.config.webhook_url || ''}
              onChange={(e) => setFormData({
                ...formData,
                config: { ...formData.config, webhookUrl: e.target.value, webhook_url: e.target.value }
              })}
              placeholder="https://hooks.slack.com/services/..."
              required
            />
            <Input
              label="Channel"
              value={formData.config.channel || ''}
              onChange={(e) => setFormData({ ...formData, config: { ...formData.config, channel: e.target.value }})}
              placeholder="#alerts"
            />
          </>
        )
      case 'teams':
        return (
          <Input
            label="Webhook URL"
            value={formData.config.webhookUrl || formData.config.webhook_url || ''}
            onChange={(e) => setFormData({
              ...formData,
              config: { ...formData.config, webhookUrl: e.target.value, webhook_url: e.target.value }
            })}
            placeholder="https://outlook.office.com/webhook/..."
            required
          />
        )
      case 'webhook':
        return (
          <>
            <Input
              label="Webhook URL"
              value={formData.config.url || ''}
              onChange={(e) => setFormData({ ...formData, config: { ...formData.config, url: e.target.value }})}
              placeholder="https://example.com/webhook"
              required
            />
            <Select
              label="HTTP Method"
              value={formData.config.method || 'POST'}
              onChange={(e) => setFormData({ ...formData, config: { ...formData.config, method: e.target.value }})}
            >
              <option value="POST">POST</option>
              <option value="PUT">PUT</option>
            </Select>
          </>
        )
      case 'pagerduty':
        return (
          <Input
            label="Integration Key"
            value={formData.config.integrationKey || formData.config.routing_key || ''}
            onChange={(e) => setFormData({
              ...formData,
              config: { ...formData.config, integrationKey: e.target.value, routing_key: e.target.value }
            })}
            placeholder="Your PagerDuty integration key"
            required
          />
        )
      case 'opsgenie':
        return (
          <>
            <Input
              label="API Key"
              value={formData.config.apiKey || formData.config.api_key || ''}
              onChange={(e) => setFormData({
                ...formData,
                config: { ...formData.config, apiKey: e.target.value, api_key: e.target.value }
              })}
              placeholder="Your Opsgenie API key"
              required
            />
            <Input
              label="API URL"
              value={formData.config.apiUrl || formData.config.api_url || 'https://api.opsgenie.com'}
              onChange={(e) => setFormData({
                ...formData,
                config: { ...formData.config, apiUrl: e.target.value, api_url: e.target.value }
              })}
            />
          </>
        )
      default:
        return null
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Input
          label="Channel Name"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          required
          placeholder="e.g., Team Slack Channel"
        />
        <Select
          label="Channel Type"
          value={formData.type}
          onChange={(e) => setFormData({ ...formData, type: e.target.value, config: {} })}
        >
          <option value="email">Email</option>
          <option value="slack">Slack</option>
          <option value="teams">Microsoft Teams</option>
          <option value="webhook">Webhook</option>
          <option value="pagerduty">PagerDuty</option>
          <option value="opsgenie">Opsgenie</option>
        </Select>
      </div>

      {renderConfigFields()}

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="channel-enabled"
          checked={formData.enabled}
          onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
          className="w-4 h-4"
        />
        <label htmlFor="channel-enabled" className="text-sm text-sre-text">Enable this channel</label>
      </div>

      {/* Visibility Settings */}
      <div className="border-t border-sre-border pt-4 space-y-3">
        <div>
          <label htmlFor="channel-visibility" className="block text-sm font-semibold text-sre-text mb-2">
            <span className="material-icons text-sm align-middle mr-1">visibility</span>{' '}
            Visibility
          </label>
          <Select
            id="channel-visibility"
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
            {formData.visibility === 'private' && 'Only you can view and edit this channel'}
            {formData.visibility === 'group' && 'Users in selected groups can view this channel'}
            {formData.visibility === 'tenant' && 'All users in your organization can view this channel'}
          </p>
        </div>

        {/* Group Sharing - only show when visibility is 'group' */}
        {formData.visibility === 'group' && groups?.length > 0 && (
          <div>
            <label htmlFor="channel-groups" className="block text-sm font-medium text-sre-text mb-2">
              Share with Groups
            </label>
            <div id="channel-groups" className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-48 overflow-y-auto p-2 border border-sre-border rounded bg-sre-surface">
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
          <span className="material-icons text-sm mr-2">save</span>{' '}
          Save Channel
        </Button>
      </div>
    </form>
  )
}

ChannelEditor.propTypes = {
  channel: PropTypes.shape({
    name: PropTypes.string,
    type: PropTypes.string,
    enabled: PropTypes.bool,
    config: PropTypes.object,
    sharedGroupIds: PropTypes.arrayOf(PropTypes.string),
  }),
  onSave: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
}
