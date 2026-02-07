import { useState } from 'react'
import PropTypes from 'prop-types'
import { Button, Input, Select } from '../ui'

/**
 * ChannelEditor component
 * @param {object} props - Component props
 */
export default function ChannelEditor({ channel, onSave, onCancel }) {
  const [formData, setFormData] = useState(channel || {
    name: '',
    type: 'webhook',
    enabled: true,
    config: {}
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave(formData)
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
  }),
  onSave: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
}
