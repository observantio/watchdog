/**
 * API client for beObservant backend
 */
import { API_BASE } from './utils/constants'

let authToken = null
let userOrgIds = []
let isPromotingOrgId = false

export function setAuthToken(token) {
  authToken = token
}

export function setUserOrgIds(orgIds) {
  if (Array.isArray(orgIds) && orgIds.length > 0) {
    userOrgIds = [orgIds[0]]
  } else if (typeof orgIds === 'string' && orgIds) {
    userOrgIds = [orgIds]
  } else {
    userOrgIds = []
  }
}

export function getUserOrgIds() {
  return userOrgIds && userOrgIds.length > 0 ? userOrgIds : []
}

async function promoteOrgId(orgId) {
  if (!authToken || !orgId || isPromotingOrgId) return
  if (userOrgIds[0] === orgId) return
  isPromotingOrgId = true
  try {
    await fetch(`${API_BASE}/api/auth/me`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({ org_id: orgId })
    })
    userOrgIds = [orgId, ...userOrgIds.filter((id) => id !== orgId)]
  } catch (e) {
    console.error('Failed to promote org ID', e)
  } finally {
    isPromotingOrgId = false
  }
}

async function requestWithHeaders(path, opts = {}, headers = {}) {
  const merged = { ...headers, ...opts.headers }
  if (authToken) {
    merged['Authorization'] = `Bearer ${authToken}`
  }
  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers: merged })
  if (!res.ok) {
    const text = await res.text()
    let body
    try {
      body = text?.startsWith('{') ? JSON.parse(text) : { message: text }
      globalThis.window.dispatchEvent(new CustomEvent('api-error', { detail: { status: res.status, body } }))
    } catch (e) {
      body = { message: text || res.statusText }
      globalThis.window.dispatchEvent(new CustomEvent('api-error', { detail: { status: res.status, body } }))
      console.error('Failed to parse error response', e)
    }

    if (res.status === 401 && path !== '/api/auth/login') {
      authToken = null
      localStorage.removeItem('auth_token')
      globalThis.window.location.href = '/login'
    }

    const err = new Error(text || res.statusText)
    err.status = res.status
    try {
      if (body !== undefined) {
        err.body = body
      } else if (text?.startsWith('{')) {
        err.body = JSON.parse(text)
      }
    } catch (e) {
      console.error('Failed to parse error response', e)
    }
    throw err
  }

  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return await res.json()
  return await res.text()
}

async function request(path, opts = {}) {
  const isLokiTempo = path.includes('/api/loki') || path.includes('/api/tempo')
  const isAlertmanager = path.includes('/api/alertmanager')

  if (isLokiTempo && userOrgIds && userOrgIds.length > 0) {
    return requestWithHeaders(path, opts, { 'X-Scope-OrgID': userOrgIds[0] })
  }

  if (isAlertmanager && userOrgIds && userOrgIds.length > 0) {
    return requestWithHeaders(path, opts, { 'X-Scope-OrgID': userOrgIds.join('|') })
  }

  return requestWithHeaders(path, opts)
}

// Health & Info
export async function fetchInfo() {
  return request(`/`)
}
export async function fetchHealth() {
  return request(`/health`)
}

export async function fetchSystemMetrics() {
  return request('/api/system/metrics')
}

export async function login(username, password) {
  return request('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  })
}

export async function register(username, email, password, full_name) {
  return request('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, email, password, full_name })
  })
}

export async function getCurrentUser() {
  return request('/api/auth/me')
}

export async function updateCurrentUser(updates) {
  return request('/api/auth/me', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates)
  })
}

export async function listApiKeys() {
  return request('/api/auth/api-keys')
}

export async function createApiKey(payload) {
  return request('/api/auth/api-keys', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}

export async function updateApiKey(keyId, payload) {
  return request(`/api/auth/api-keys/${keyId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}

export async function deleteApiKey(keyId) {
  return request(`/api/auth/api-keys/${keyId}`, {
    method: 'DELETE'
  })
}

export async function getUsers() {
  return request('/api/auth/users')
}

export async function createUser(user) {
  return request('/api/auth/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(user)
  })
}

export async function updateUser(userId, user) {
  return request(`/api/auth/users/${userId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(user)
  })
}

export async function deleteUser(userId) {
  return request(`/api/auth/users/${userId}`, {
    method: 'DELETE'
  })
}

export async function getGroups() {
  return request('/api/auth/groups')
}

export async function createGroup(group) {
  return request('/api/auth/groups', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(group)
  })
}

export async function updateGroup(groupId, group) {
  return request(`/api/auth/groups/${groupId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(group)
  })
}

export async function deleteGroup(groupId) {
  return request(`/api/auth/groups/${groupId}`, {
    method: 'DELETE'
  })
}

// Permission Management
export async function getPermissions() {
  return request('/api/auth/permissions')
}

export async function getRoleDefaults() {
  return request('/api/auth/role-defaults')
}

export async function fetchTraceMetrics(params = {}) {
  const search = new URLSearchParams(params)
  const qs = search.toString()
  const path = qs ? `/api/tempo/metrics?${qs}` : '/api/tempo/metrics'
  return request(path)
}

export async function updateUserPermissions(userId, permissions) {
  return request(`/api/auth/users/${userId}/permissions`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(permissions)
  })
}

export async function updateGroupPermissions(groupId, permissions) {
  return request(`/api/auth/groups/${groupId}/permissions`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(permissions)
  })
}

export async function updateUserPassword(userId, passwords) {
  return request(`/api/auth/users/${userId}/password`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(passwords)
  })
}

export async function getActiveAgents() {
  return request('/api/agents/active')
}

// Alias for backward compatibility
export const updatePassword = updateUserPassword

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
  const params = new URLSearchParams()
  params.append('query', query)
  params.append('limit', limit.toString())
  if (start) params.append('start', start)
  if (end) params.append('end', end)
  if (direction) params.append('direction', direction)
  if (step) params.append('step', step)
  return request(`/api/loki/query?${params.toString()}`)
}
export async function getLabels() {
  return request('/api/loki/labels')
}
export async function getLabelValues(label, { query, start, end } = {}) {
  const params = new URLSearchParams()
  if (query) params.append('query', query)
  if (start) params.append('start', start)
  if (end) params.append('end', end)
  const queryString = params.toString()
  const suffix = queryString ? '?' + queryString : ''
  return request(`/api/loki/label/${encodeURIComponent(label)}/values${suffix}`)
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
  const params = new URLSearchParams()
  params.append('query', query)
  params.append('step', step.toString())
  if (start) params.append('start', start)
  if (end) params.append('end', end)
  return request(`/api/loki/aggregate?${params.toString()}`)
}
export async function getLogVolume(query, { start, end, step = 300 } = {}) {
  const params = new URLSearchParams()
  params.append('query', query)
  params.append('step', step.toString())
  if (start) params.append('start', start)
  if (end) params.append('end', end)
  return request(`/api/loki/volume?${params.toString()}`)
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
  const url = q ? `/api/grafana/dashboards/search?query=${encodeURIComponent(q)}` : '/api/grafana/dashboards/search'
  return request(url)
}
export async function getDashboard(uid) {
  return request(`/api/grafana/dashboards/${encodeURIComponent(uid)}`)
}
export async function createDashboard(payload, queryParams = '') {
  const url = queryParams ? `/api/grafana/dashboards?${queryParams}` : '/api/grafana/dashboards'
  return request(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}
export async function updateDashboard(uid, payload, queryParams = '') {
  const url = queryParams ? `/api/grafana/dashboards/${encodeURIComponent(uid)}?${queryParams}` : `/api/grafana/dashboards/${encodeURIComponent(uid)}`
  return request(url, {
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
export async function createDatasource(payload, queryParams = '') {
  const url = queryParams ? `/api/grafana/datasources?${queryParams}` : '/api/grafana/datasources'
  return request(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
}
export async function updateDatasource(uid, payload, queryParams = '') {
  const url = queryParams ? `/api/grafana/datasources/${encodeURIComponent(uid)}?${queryParams}` : `/api/grafana/datasources/${encodeURIComponent(uid)}`
  return request(url, {
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
