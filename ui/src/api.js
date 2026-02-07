/**
 * API client for beObservant backend
 */
import { API_BASE, API_KEY } from './utils/constants'

/**
 * Make an HTTP request to the API
 * @param {string} path - API endpoint path
 * @param {object} opts - Fetch options
 * @returns {Promise<any>} Response data
 */
async function request(path, opts = {}) {
  const headers = opts.headers || {}
  if (API_KEY) headers['X-API-Key'] = API_KEY
  opts.headers = headers

  const res = await fetch(`${API_BASE}${path}`, opts)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return await res.json()
  return await res.text()
}

// Health & Info
export async function fetchInfo() {
  return request(`/`)
}
export async function fetchHealth() {
  return request(`/health`)
}

// AlertManager
export async function getAlerts() {
  return request('/api/alertmanager/alerts')
}
export async function getAlertGroups() {
  return request('/api/alertmanager/alerts/groups')
}
export async function getSilences() {
  return request('/api/alertmanager/silences')
}
export async function createSilence(payload) {
  return request('/api/alertmanager/silences', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}
export async function deleteSilence(silenceId) {
  return request(`/api/alertmanager/silences/${encodeURIComponent(silenceId)}`, {
    method: 'DELETE'
  })
}
export async function postAlerts(payload) {
  return request('/api/alertmanager/alerts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}
export async function deleteAlerts(filter) {
  return request(`/api/alertmanager/alerts?filter_labels=${encodeURIComponent(JSON.stringify(filter))}`, {
    method: 'DELETE'
  })
}
export async function getAlertRules() {
  return request('/api/alertmanager/rules')
}
export async function createAlertRule(payload) {
  return request('/api/alertmanager/rules', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}
export async function updateAlertRule(ruleId, payload) {
  return request(`/api/alertmanager/rules/${encodeURIComponent(ruleId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}
export async function deleteAlertRule(ruleId) {
  return request(`/api/alertmanager/rules/${encodeURIComponent(ruleId)}`, {
    method: 'DELETE'
  })
}
export async function testAlertRule(ruleId) {
  return request(`/api/alertmanager/rules/${encodeURIComponent(ruleId)}/test`, {
    method: 'POST'
  })
}
export async function getNotificationChannels() {
  return request('/api/alertmanager/channels')
}
export async function createNotificationChannel(payload) {
  return request('/api/alertmanager/channels', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}
export async function updateNotificationChannel(channelId, payload) {
  return request(`/api/alertmanager/channels/${encodeURIComponent(channelId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}
export async function deleteNotificationChannel(channelId) {
  return request(`/api/alertmanager/channels/${encodeURIComponent(channelId)}`, {
    method: 'DELETE'
  })
}
export async function testNotificationChannel(channelId) {
  return request(`/api/alertmanager/channels/${encodeURIComponent(channelId)}/test`, {
    method: 'POST'
  })
}

// Loki
export async function queryLogs({ query, limit = 100, start, end, direction = 'backward', step }) {
  const qs = []
  qs.push(`query=${encodeURIComponent(query)}`)
  qs.push(`limit=${limit}`)
  if (start) qs.push(`start=${start}`)
  if (end) qs.push(`end=${end}`)
  if (direction) qs.push(`direction=${encodeURIComponent(direction)}`)
  if (step) qs.push(`step=${step}`)
  return request(`/api/loki/query?${qs.join('&')}`)
}
export async function getLabels() {
  return request('/api/loki/labels')
}
export async function getLabelValues(label, { query, start, end } = {}) {
  const qs = []
  if (query) qs.push(`query=${encodeURIComponent(query)}`)
  if (start) qs.push(`start=${start}`)
  if (end) qs.push(`end=${end}`)
  return request(`/api/loki/label/${encodeURIComponent(label)}/values${qs.length ? `?${qs.join('&')}` : ''}`)
}
export async function searchLogs({ pattern, labels, start, end, limit = 100 }) {
  return request('/api/loki/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pattern, labels, start, end, limit })
  })
}
export async function filterLogs({ labels, filters, start, end, limit = 100 }) {
  return request('/api/loki/filter', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ labels, filters, start, end, limit })
  })
}
export async function aggregateLogs(query, { start, end, step = 60 } = {}) {
  const qs = []
  qs.push(`query=${encodeURIComponent(query)}`)
  qs.push(`step=${step}`)
  if (start) qs.push(`start=${start}`)
  if (end) qs.push(`end=${end}`)
  return request(`/api/loki/aggregate?${qs.join('&')}`)
}
export async function getLogVolume(query, { start, end, step = 300 } = {}) {
  const qs = []
  qs.push(`query=${encodeURIComponent(query)}`)
  qs.push(`step=${step}`)
  if (start) qs.push(`start=${start}`)
  if (end) qs.push(`end=${end}`)
  return request(`/api/loki/volume?${qs.join('&')}`)
}

// Tempo
export async function searchTraces({ service, operation, minDuration, maxDuration, start, end, limit = 100 }) {
  const qs = []
  if (service) qs.push(`service=${encodeURIComponent(service)}`)
  if (operation) qs.push(`operation=${encodeURIComponent(operation)}`)
  if (minDuration) qs.push(`minDuration=${encodeURIComponent(minDuration)}`)
  if (maxDuration) qs.push(`maxDuration=${encodeURIComponent(maxDuration)}`)
  if (start) qs.push(`start=${start}`)
  if (end) qs.push(`end=${end}`)
  qs.push(`limit=${limit}`)
  return request(`/api/tempo/traces/search?${qs.join('&')}`)
}
export async function fetchTempoServices() {
  return request('/api/tempo/services')
}
export async function getTrace(traceID) {
  return request(`/api/tempo/traces/${encodeURIComponent(traceID)}`)
}

// Grafana
export async function searchDashboards(q = '') {
  return request(`/api/grafana/dashboards/search${q ? `?query=${encodeURIComponent(q)}` : ''}`)
}
export async function getDashboard(uid) {
  return request(`/api/grafana/dashboards/${encodeURIComponent(uid)}`)
}
export async function createDashboard(payload) {
  return request('/api/grafana/dashboards', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}
export async function updateDashboard(uid, payload) {
  return request(`/api/grafana/dashboards/${encodeURIComponent(uid)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}
export async function deleteDashboard(uid) {
  return request(`/api/grafana/dashboards/${encodeURIComponent(uid)}`, {
    method: 'DELETE'
  })
}

export async function getDatasources() {
  return request('/api/grafana/datasources')
}
export async function getDatasource(uid) {
  return request(`/api/grafana/datasources/uid/${encodeURIComponent(uid)}`)
}
export async function createDatasource(payload) {
  return request('/api/grafana/datasources', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}
export async function updateDatasource(uid, payload) {
  return request(`/api/grafana/datasources/${encodeURIComponent(uid)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}
export async function deleteDatasource(uid) {
  return request(`/api/grafana/datasources/${encodeURIComponent(uid)}`, {
    method: 'DELETE'
  })
}

export async function getFolders() {
  return request('/api/grafana/folders')
}
export async function createFolder(title) {
  return request('/api/grafana/folders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title })
  })
}
export async function deleteFolder(uid) {
  return request(`/api/grafana/folders/${encodeURIComponent(uid)}`, {
    method: 'DELETE'
  })
}

export default { fetchInfo }
