export const ALERTMANAGER_METRIC_ORDER_KEY = 'alertmanager-metric-order'
export const DEFAULT_ALERTMANAGER_METRIC_KEYS = ['activeAlerts', 'alertRules', 'channels', 'silences']

export const EMPTY_CONFIRM_DIALOG = {
  isOpen: false,
  title: '',
  message: '',
  onConfirm: null,
  confirmText: 'Delete',
  variant: 'danger',
}

const CHANNEL_MAPPINGS = {
  email: {
    smtpHost: 'smtp_host',
    smtpPort: 'smtp_port',
    smtpUsername: 'smtp_username',
    smtpPassword: 'smtp_password',
    smtpFrom: 'smtp_from',
    smtpStartTLS: 'smtp_starttls',
    smtpUseSSL: 'smtp_use_ssl',
    smtpAuthType: 'smtp_auth_type',
    smtpApiKey: 'smtp_api_key',
    emailProvider: 'email_provider',
    sendgridApiKey: 'sendgrid_api_key',
    resendApiKey: 'resend_api_key',
    apiKey: 'api_key',
  },
  slack: { webhookUrl: 'webhook_url' },
  teams: { webhookUrl: 'webhook_url' },
  pagerduty: { integrationKey: 'routing_key' },
}

export function normalizeChannelPayload(channelData) {
  const normalized = { ...channelData, config: channelData.config || {} }
  const map = CHANNEL_MAPPINGS[normalized.type]
  if (!map) return normalized

  for (const [from, to] of Object.entries(map)) {
    if (normalized.config[from] && !normalized.config[to]) {
      normalized.config[to] = normalized.config[from]
    }
  }

  return normalized
}

export function readMetricOrderFromStorage(storage = globalThis.localStorage) {
  try {
    const raw = storage.getItem(ALERTMANAGER_METRIC_ORDER_KEY)
    if (!raw) return DEFAULT_ALERTMANAGER_METRIC_KEYS
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return DEFAULT_ALERTMANAGER_METRIC_KEYS
    const values = new Set(parsed)
    if (!DEFAULT_ALERTMANAGER_METRIC_KEYS.every((key) => values.has(key))) {
      return DEFAULT_ALERTMANAGER_METRIC_KEYS
    }
    return parsed
  } catch {
    return DEFAULT_ALERTMANAGER_METRIC_KEYS
  }
}

export function writeMetricOrderToStorage(metricOrder, storage = globalThis.localStorage) {
  try {
    storage.setItem(ALERTMANAGER_METRIC_ORDER_KEY, JSON.stringify(metricOrder))
  } catch {
    // ignore storage errors
  }
}
