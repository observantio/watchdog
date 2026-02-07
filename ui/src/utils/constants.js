/**
 * Application-wide constants
 */

// API Configuration
export const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:4319'
export const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL || 'https://localhost/grafana'

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
  { value: 'prometheus', label: 'Prometheus' },
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
  { value: 'opsgenie', label: 'Opsgenie' },
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
  min: 100000000, // 100ms
  max: 5000000000, // 5s
  step: 50000000, // 50ms
}
