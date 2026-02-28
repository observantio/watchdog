// API Configuration
function resolveDefaultApiBase() {
  if (typeof globalThis === 'undefined' || !globalThis.location) {
    return 'http://localhost:4319'
  }
  const { protocol, hostname } = globalThis.location
  return `${protocol}//${hostname}:4319`
}

export const API_BASE = import.meta.env.VITE_API_URL || resolveDefaultApiBase()
export const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL || 'http://localhost:8080/grafana'
export const OIDC_PROVIDER_LABEL =  'SSO'
// External service endpoints (configurable via Vite env)
export const LOKI_OTLP_ENDPOINT = import.meta.env.VITE_LOKI_OTLP_ENDPOINT || 'http://loki:3100/otlp'
export const LOKI_BASE = import.meta.env.VITE_LOKI_URL || 'http://loki:3100'
export const MIMIR_REMOTE_WRITE = import.meta.env.VITE_MIMIR_REMOTE_WRITE || 'http://mimir:9009/api/v1/push'
export const MIMIR_PROMETHEUS_URL = import.meta.env.VITE_MIMIR_PROMETHEUS_URL || 'http://mimir:9009/prometheus'
export const TEMPO_URL = import.meta.env.VITE_TEMPO_URL || 'http://tempo:3200'
export const TEMPO_OTLP_ENDPOINT = import.meta.env.VITE_TEMPO_OTLP_ENDPOINT || 'tempo:4317'
// OTLP Gateway host used by UI when generating agent configs
export const OTLP_GATEWAY_HOST = import.meta.env.VITE_OTLP_GATEWAY_HOST || 'http://localhost:4320'

// Time ranges (in minutes)
export const TIME_RANGES = [
  { value: 5, label: 'Last 5 minutes' },
  { value: 15, label: 'Last 15 minutes' },
  { value: 60, label: 'Last 1 hour' },
  { value: 180, label: 'Last 3 hours' },
  { value: 360, label: 'Last 6 hours' },
  { value: 720, label: 'Last 12 hours' },
  { value: 1440, label: 'Last 24 hours' },
]

// Log levels
export const LOG_LEVELS = {
  ERROR: { text: 'ERROR', color: 'text-red-400', bgClass: 'bg-red-500/20 text-red-400 border-red-500/30' },
  FATAL: { text: 'FATAL', color: 'text-red-500', bgClass: 'bg-red-500/20 text-red-400 border-red-500/30' },
  WARN: { text: 'WARN', color: 'text-yellow-400', bgClass: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' },
  INFO: { text: 'INFO', color: 'text-blue-400', bgClass: 'bg-blue-500/20 text-blue-400 border-blue-500/30' },
  DEBUG: { text: 'DEBUG', color: 'text-gray-400', bgClass: 'bg-gray-500/20 text-gray-400 border-gray-500/30' },
  LOG: { text: 'LOG', color: 'text-sre-text', bgClass: 'bg-sre-surface text-sre-text-muted border-sre-border' },
}

// Alert severities
export const ALERT_SEVERITIES = [
  { value: 'info', label: 'Info' },
  { value: 'warning', label: 'Warning' },
  { value: 'critical', label: 'Critical' },
]

// Datasource types
export const DATASOURCE_TYPES = [
  { value: 'prometheus', label: 'Mimir (Prometheus-compatible)' },
  { value: 'loki', label: 'Loki' },
  { value: 'tempo', label: 'Tempo' },
  { value: 'graphite', label: 'Graphite' },
  { value: 'influxdb', label: 'InfluxDB' },
  { value: 'elasticsearch', label: 'Elasticsearch' },
]

// Notification channel types
export const NOTIFICATION_CHANNEL_TYPES = [
  { value: 'email', label: 'Email' },
  { value: 'slack', label: 'Slack' },
  { value: 'teams', label: 'Microsoft Teams' },
  { value: 'webhook', label: 'Webhook' },
  { value: 'pagerduty', label: 'PagerDuty' },
]

// Status variants
export const STATUS_VARIANTS = {
  healthy: 'success',
  degraded: 'warning',
  unhealthy: 'error',
  unknown: 'default',
}

// Refresh intervals (in seconds)
export const REFRESH_INTERVALS = [
  { value: 10, label: '10s' },
  { value: 30, label: '30s' },
  { value: 60, label: '1m' },
  { value: 300, label: '5m' },
  { value: 600, label: '10m' },
]

// Default query limits
export const DEFAULT_QUERY_LIMITS = {
  logs: 100,
  traces: 100,
  alerts: 1000,
}

// Duration range defaults (in nanoseconds)
export const DEFAULT_DURATION_RANGE = {
  min: 0, // 0ms (allow timeline minimum to be zero)
  max: 5000000000, // 5s
  step: 50000000, // 50ms
}

// Navigation labels
export const NAV_ITEMS = {
  DASHBOARD: { label: 'Dashboard', icon: 'dashboard', path: '/', permission: null },
  TEMPO: { label: 'Tempo', icon: 'timeline', path: '/tempo', permission: 'read:traces' },
  LOKI: { label: 'Loki', icon: 'view_stream', path: '/loki', permission: 'read:logs' },
  RCA: { label: 'RCA', icon: 'psychology', path: '/rca', permission: 'read:rca' },
  ALERTMANAGER: { label: 'AlertManager', icon: 'notifications', path: '/alertmanager', permission: 'read:alerts' },
  INCIDENTS: { label: 'Incidents', icon: 'assignment', path: '/incidents', permission: 'read:alerts' },
  GRAFANA: { label: 'Grafana', icon: 'analytics', path: '/grafana', permission: 'read:dashboards' },
}

// View mode options for logs
export const LOG_VIEW_MODES = ['table', 'compact', 'raw']

// User roles
export const USER_ROLES = [
  { value: 'viewer', label: 'Viewer - Read-only access' },
  { value: 'user', label: 'User - Read and write access' },
  { value: 'admin', label: 'Admin - Full access' },
]

// UI Messages
export const MESSAGES = {
  NO_ACCESS: "You don't have access to this page.",
  NO_RESULTS: 'No results found',
  LOADING: 'Loading...',
  CONFIRM_DELETE: 'Are you sure? This action cannot be undone.',
  PASSWORD_MIN_LENGTH: 'Password must be at least 8 characters long',
  PASSWORD_MISMATCH: 'New passwords do not match',
  REQUIRED_FIELD: 'This field is required',
  COPIED_CLIPBOARD: 'Copied to clipboard',
  COPY_FAILED: 'Failed to copy to clipboard',
}

// Max logs options for Loki query
export const MAX_LOG_OPTIONS = [20, 50, 100,200]

// Maximum number of items to request for paginated searches (traces, logs, etc.)
export const TRACE_LIMIT_OPTIONS = [20, 50, 100, 200]

// Auto-refresh intervals for Loki
export const LOKI_REFRESH_INTERVALS = [
  { value: 10, label: '10s' },
  { value: 30, label: '30s' },
  { value: 60, label: '60s' },
  { value: 300, label: '5m' },
]

// Trace status filter options
export const TRACE_STATUS_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'ok', label: 'Success Only' },
  { value: 'error', label: 'Errors Only' },
]

// Dashboard visibility options
export const VISIBILITY_OPTIONS = [
  { value: 'private', label: 'Private (Only me)' },
  { value: 'group', label: 'Shared with Groups' },
  { value: 'tenant', label: 'Tenant-wide (Everyone in organization)' },
]

// Grafana dashboard auto-refresh intervals
export const GRAFANA_REFRESH_INTERVALS = [
  { value: '', label: 'No auto-refresh' },
  { value: '5s', label: '5 seconds' },
  { value: '10s', label: '10 seconds' },
  { value: '30s', label: '30 seconds' },
  { value: '1m', label: '1 minute' },
  { value: '5m', label: '5 minutes' },
  { value: '15m', label: '15 minutes' },
  { value: '30m', label: '30 minutes' },
  { value: '1h', label: '1 hour' },
]

// Alert severity options
export const ALERT_SEVERITY_OPTIONS = [
  { value: 'all', label: 'All Severities' },
  { value: 'critical', label: 'Critical' },
  { value: 'warning', label: 'Warning' },
  { value: 'info', label: 'Info' },
]

// Loki time range options
export const LOKI_TIME_RANGES = [
  { value: 5, label: 'Last 5 minutes' },
  { value: 15, label: 'Last 15 minutes' },
  { value: 60, label: 'Last 1 hour' },
  { value: 180, label: 'Last 3 hours' },
  { value: 360, label: 'Last 6 hours' },
  { value: 1440, label: 'Last 24 hours' },
]
