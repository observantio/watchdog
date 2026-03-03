import { API_BASE } from "./utils/constants";

let authToken = null;
let setupToken = null;
let userOrgIds = [];

export function setSetupToken(token) {
  setupToken = token;
}

export function clearSetupToken() {
  setupToken = null;
}

export function setAuthToken(token) {
  authToken = token;
}

export function setUserOrgIds(orgIds) {
  if (Array.isArray(orgIds) && orgIds.length > 0) {
    userOrgIds = [orgIds[0]];
  } else if (typeof orgIds === "string" && orgIds) {
    userOrgIds = [orgIds];
  } else {
    userOrgIds = [];
  }
}

export function getUserOrgIds() {
  return userOrgIds && userOrgIds.length > 0 ? userOrgIds : [];
}

async function requestWithHeaders(path, opts = {}, headers = {}) {
  const merged = { ...headers, ...opts.headers };
  if (authToken) {
    merged["Authorization"] = `Bearer ${authToken}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    credentials: "include",
    headers: merged,
  });
  if (!res.ok) {
    const text = await res.text();
    let body;
    try {
      body = text?.startsWith("{") ? JSON.parse(text) : { message: text };
    } catch {
      body = { message: text || res.statusText };
    }

    globalThis.window.dispatchEvent(
      new CustomEvent("api-error", { detail: { status: res.status, body } }),
    );

    const isAuthLoginEndpoint =
      path === "/api/auth/login" || path === "/api/auth/oidc/exchange";
    if (res.status === 401 && !isAuthLoginEndpoint) {
      authToken = null;
      globalThis.window.dispatchEvent(
        new CustomEvent("session-expired", { detail: { status: 401 } }),
      );
    }

    const err = new Error(
      body?.message || body?.detail || text || res.statusText,
    );
    err.status = res.status;
    err.body = body;
    throw err;
  }

  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return await res.json();
  return await res.text();
}

async function request(path, opts = {}) {
  const isLokiTempo = path.includes("/api/loki") || path.includes("/api/tempo");
  const isBeCertain = path.includes("/api/becertain");
  const isAlertmanager = path.includes("/api/alertmanager");

  if ((isLokiTempo || isBeCertain) && userOrgIds && userOrgIds.length > 0) {
    return requestWithHeaders(path, opts, { "X-Scope-OrgID": userOrgIds[0] });
  }

  if (isAlertmanager && userOrgIds && userOrgIds.length > 0) {
    return requestWithHeaders(path, opts, {
      "X-Scope-OrgID": userOrgIds.join("|"),
    });
  }

  return requestWithHeaders(path, opts);
}

function requestJson(
  path,
  { method = "POST", payload, headers = {}, ...opts } = {},
) {
  const body = payload === undefined ? undefined : JSON.stringify(payload);
  return request(path, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    ...(body !== undefined ? { body } : {}),
    ...opts,
  });
}

export async function fetchInfo() {
  return request(`/`);
}
export async function fetchHealth() {
  return request(`/health`);
}

export async function fetchSystemMetrics() {
  return request("/api/system/metrics");
}

export async function login(username, password, mfa_code) {
  const payload = { username, password };
  if (mfa_code) payload.mfa_code = mfa_code;
  return requestJson("/api/auth/login", { payload });
}

export async function refreshSession() {
  return request("/api/auth/refresh", { method: "POST" });
}

export async function enrollMFA() {
  if (authToken) return requestJson("/api/auth/mfa/enroll", { method: "POST" });
  if (!setupToken) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/auth/mfa/enroll`, {
    method: "POST",
    credentials: "include",
    headers: { Authorization: `Bearer ${setupToken}` },
  });
  if (!res.ok) {
    const text = await res.text();
    let body;
    try {
      body = text?.startsWith("{") ? JSON.parse(text) : { message: text };
    } catch {
      body = { message: text };
    }
    const msg = body.message || body.detail || text || res.statusText;
    const err = new Error(msg);
    err.body = body;
    throw err;
  }
  return await res.json();
}

export async function verifyMFA(code) {
  if (authToken)
    return requestJson("/api/auth/mfa/verify", {
      method: "POST",
      payload: { code },
    });
  if (!setupToken) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/auth/mfa/verify`, {
    method: "POST",
    credentials: "include",
    headers: {
      Authorization: `Bearer ${setupToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) {
    const text = await res.text();
    let body;
    try {
      body = text?.startsWith("{") ? JSON.parse(text) : { message: text };
    } catch {
      body = { message: text };
    }
    const msg = body.message || body.detail || text || res.statusText;
    const err = new Error(msg);
    err.body = body;
    throw err;
  }
  return await res.json();
}

export async function disableMFA({ current_password, code } = {}) {
  return requestJson("/api/auth/mfa/disable", {
    method: "POST",
    payload: { current_password, code },
  });
}

export async function logout() {
  return request("/api/auth/logout", { method: "POST" });
}

export async function resetUserMFA(userId) {
  return request(`/api/auth/users/${encodeURIComponent(userId)}/mfa/reset`, {
    method: "POST",
  });
}

export async function resetUserPasswordTemp(userId) {
  return requestJson(
    `/api/auth/users/${encodeURIComponent(userId)}/password/reset-temp`,
    { method: "POST" },
  );
}

export async function getAuthMode() {
  return request("/api/auth/mode");
}

export async function getOIDCAuthorizeUrl(
  redirect_uri,
  {
    state = null,
    nonce = null,
    code_challenge = null,
    code_challenge_method = null,
  } = {},
) {
  return requestJson("/api/auth/oidc/authorize-url", {
    payload: {
      redirect_uri,
      state,
      nonce,
      code_challenge,
      code_challenge_method,
    },
  });
}

export async function exchangeOIDCCode(
  code,
  redirect_uri,
  { state = null, transaction_id = null, code_verifier = null } = {},
) {
  return requestJson("/api/auth/oidc/exchange", {
    payload: { code, redirect_uri, state, transaction_id, code_verifier },
  });
}

export async function register(username, email, password, full_name) {
  return requestJson("/api/auth/register", {
    payload: { username, email, password, full_name },
  });
}

export async function getCurrentUser() {
  return request("/api/auth/me");
}

export async function getCurrentUserNoRedirect() {
  const res = await fetch(`${API_BASE}/api/auth/me`, {
    credentials: "include",
  });
  if (!res.ok) {
    const text = await res.text();
    let body;
    try {
      body = text?.startsWith("{") ? JSON.parse(text) : { message: text };
    } catch {
      body = { message: text || res.statusText };
    }
    const err = new Error(
      body?.message || body?.detail || text || res.statusText,
    );
    err.status = res.status;
    err.body = body;
    throw err;
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return await res.json();
  return await res.text();
}

export async function updateCurrentUser(updates) {
  return requestJson("/api/auth/me", { method: "PUT", payload: updates });
}

export async function listApiKeys({ showHidden = false } = {}) {
  const params = new URLSearchParams();
  if (showHidden) params.set("show_hidden", "true");
  const qs = params.toString() ? `?${params.toString()}` : "";
  return request(`/api/auth/api-keys${qs}`);
}

export async function setApiKeyHidden(keyId, hidden = true) {
  return requestJson(`/api/auth/api-keys/${encodeURIComponent(keyId)}/hide`, {
    method: "POST",
    payload: { hidden: !!hidden },
  });
}

export async function createApiKey(payload) {
  return requestJson("/api/auth/api-keys", { payload });
}

export async function updateApiKey(keyId, payload) {
  return requestJson(`/api/auth/api-keys/${keyId}`, {
    method: "PATCH",
    payload,
  });
}

export async function regenerateApiKeyOtlpToken(keyId) {
  return requestJson(`/api/auth/api-keys/${keyId}/otlp-token/regenerate`, {
    method: "POST",
  });
}

export async function deleteApiKey(keyId) {
  return request(`/api/auth/api-keys/${keyId}`, {
    method: "DELETE",
  });
}

export async function getApiKeyShares(keyId) {
  return request(`/api/auth/api-keys/${keyId}/shares`);
}

export async function replaceApiKeyShares(keyId, userIds, groupIds = []) {
  return requestJson(`/api/auth/api-keys/${keyId}/shares`, {
    method: "PUT",
    payload: { user_ids: userIds, group_ids: groupIds },
  });
}

export async function deleteApiKeyShare(keyId, userId) {
  return request(`/api/auth/api-keys/${keyId}/shares/${userId}`, {
    method: "DELETE",
  });
}

export async function getAuditLogs(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && `${value}` !== "") {
      search.set(key, String(value));
    }
  });
  const qs = search.toString();
  return request(`/api/auth/audit-logs${qs ? `?${qs}` : ""}`);
}

export async function exportAuditLogs(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && `${value}` !== "") {
      search.set(key, String(value));
    }
  });
  const qs = search.toString();
  const path = `/api/auth/audit-logs/export${qs ? `?${qs}` : ""}`;
  const res = await request(path);
  return res;
}

export async function getUsers() {
  return request("/api/auth/users");
}

export async function createUser(user) {
  return requestJson("/api/auth/users", { payload: user });
}

export async function updateUser(userId, user) {
  return requestJson(`/api/auth/users/${userId}`, {
    method: "PUT",
    payload: user,
  });
}

export async function deleteUser(userId) {
  return request(`/api/auth/users/${userId}`, {
    method: "DELETE",
  });
}

export async function getGroups() {
  return request("/api/auth/groups");
}

export async function createGroup(group) {
  return requestJson("/api/auth/groups", { payload: group });
}

export async function updateGroup(groupId, group) {
  return requestJson(`/api/auth/groups/${groupId}`, {
    method: "PUT",
    payload: group,
  });
}

export async function deleteGroup(groupId) {
  return request(`/api/auth/groups/${groupId}`, {
    method: "DELETE",
  });
}

export async function updateGroupMembers(groupId, userIds) {
  return requestJson(`/api/auth/groups/${groupId}/members`, {
    method: "PUT",
    payload: { user_ids: userIds },
  });
}

export async function getPermissions() {
  return request("/api/auth/permissions");
}

export async function getRoleDefaults() {
  return request("/api/auth/role-defaults");
}

export async function updateUserPermissions(userId, permissions) {
  return requestJson(`/api/auth/users/${userId}/permissions`, {
    method: "PUT",
    payload: permissions,
  });
}

export async function updateGroupPermissions(groupId, permissions) {
  return requestJson(`/api/auth/groups/${groupId}/permissions`, {
    method: "PUT",
    payload: permissions,
  });
}

export async function updateUserPassword(userId, passwords) {
  return requestJson(`/api/auth/users/${userId}/password`, {
    method: "PUT",
    payload: passwords,
  });
}

export async function getActiveAgents() {
  return request("/api/agents/active");
}

export const updatePassword = updateUserPassword;

export async function getAlerts({ showHidden = false } = {}) {
  const params = new URLSearchParams();
  if (showHidden) params.set("show_hidden", "true");
  const qs = params.toString() ? `?${params.toString()}` : "";
  return request(`/api/alertmanager/alerts${qs}`);
}

export async function getAlertsByFilter(filter = {}, active = true) {
  const params = new URLSearchParams();
  if (filter && Object.keys(filter).length > 0)
    params.set("filter_labels", JSON.stringify(filter));
  if (typeof active !== "undefined" && active !== null)
    params.set("active", String(active));
  const qs = params.toString() ? `?${params.toString()}` : "";
  return request(`/api/alertmanager/alerts${qs}`);
}

export async function getAlertGroups() {
  return request("/api/alertmanager/alerts/groups");
}
export async function getSilences({ showHidden = false } = {}) {
  const params = new URLSearchParams();
  if (showHidden) params.set("show_hidden", "true");
  const qs = params.toString() ? `?${params.toString()}` : "";
  return request(`/api/alertmanager/silences${qs}`);
}
export async function createSilence(payload) {
  return requestJson("/api/alertmanager/silences", { payload });
}
export async function deleteSilence(silenceId) {
  return request(
    `/api/alertmanager/silences/${encodeURIComponent(silenceId)}`,
    {
      method: "DELETE",
    },
  );
}
export async function postAlerts(payload) {
  return requestJson("/api/alertmanager/alerts", { payload });
}
export async function deleteAlerts(filter) {
  return request(
    `/api/alertmanager/alerts?filter_labels=${encodeURIComponent(JSON.stringify(filter))}`,
    {
      method: "DELETE",
    },
  );
}
export async function getAlertRules({ showHidden = false } = {}) {
  const params = new URLSearchParams();
  if (showHidden) params.set("show_hidden", "true");
  const qs = params.toString() ? `?${params.toString()}` : "";
  return request(`/api/alertmanager/rules${qs}`);
}
export async function setAlertRuleHidden(ruleId, hidden = true) {
  return requestJson(`/api/alertmanager/rules/${encodeURIComponent(ruleId)}/hide`, {
    method: "POST",
    payload: { hidden: !!hidden },
  });
}
export async function setSilenceHidden(silenceId, hidden = true) {
  return requestJson(`/api/alertmanager/silences/${encodeURIComponent(silenceId)}/hide`, {
    method: "POST",
    payload: { hidden: !!hidden },
  });
}
export async function getPublicAlertRules() {
  return request("/api/alertmanager/public/rules");
}
export async function getIncidents(status, visibility, groupId) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (visibility) params.set("visibility", visibility);
  if (groupId) params.set("group_id", groupId);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return request(`/api/alertmanager/incidents${qs}`);
}
export async function updateIncident(incidentId, payload) {
  return requestJson(
    `/api/alertmanager/incidents/${encodeURIComponent(incidentId)}`,
    {
      method: "PATCH",
      payload,
    },
  );
}

export async function createIncidentJira(incidentId, payload) {
  return requestJson(
    `/api/alertmanager/incidents/${encodeURIComponent(incidentId)}/jira`,
    {
      method: "POST",
      payload,
    },
  );
}
export async function getJiraConfig() {
  return request("/api/alertmanager/jira/config");
}
export async function updateJiraConfig(payload) {
  return requestJson("/api/alertmanager/jira/config", {
    method: "PUT",
    payload,
  });
}
export async function listJiraProjects() {
  return request("/api/alertmanager/jira/projects");
}
export async function listJiraProjectsByIntegration(integrationId) {
  return request(
    `/api/alertmanager/integrations/jira/${encodeURIComponent(integrationId)}/projects`,
  );
}
export async function listJiraIssueTypes(projectKey, integrationId) {
  if (integrationId) {
    return request(
      `/api/alertmanager/integrations/jira/${encodeURIComponent(integrationId)}/projects/${encodeURIComponent(projectKey)}/issue-types`,
    );
  }
  return request(
    `/api/alertmanager/jira/projects/${encodeURIComponent(projectKey)}/issue-types`,
  );
}
export async function listIncidentJiraComments(incidentId) {
  return request(
    `/api/alertmanager/incidents/${encodeURIComponent(incidentId)}/jira/comments`,
  );
}
export async function syncIncidentJiraNotes(incidentId) {
  return requestJson(
    `/api/alertmanager/incidents/${encodeURIComponent(incidentId)}/jira/sync-notes`,
    { method: "POST" },
  );
}
export async function importAlertRules(payload) {
  return requestJson("/api/alertmanager/rules/import", {
    method: "POST",
    payload,
  });
}
export async function getAllowedChannelTypes() {
  return request("/api/alertmanager/integrations/channel-types");
}
export async function listJiraIntegrations({ showHidden = false } = {}) {
  const params = new URLSearchParams();
  if (showHidden) params.set("show_hidden", "true");
  const qs = params.toString() ? `?${params.toString()}` : "";
  return request(`/api/alertmanager/integrations/jira${qs}`);
}
export async function setJiraIntegrationHidden(integrationId, hidden = true) {
  return requestJson(
    `/api/alertmanager/integrations/jira/${encodeURIComponent(integrationId)}/hide`,
    { method: "POST", payload: { hidden: !!hidden } },
  );
}
export async function createJiraIntegration(payload) {
  return requestJson("/api/alertmanager/integrations/jira", {
    method: "POST",
    payload,
  });
}
export async function updateJiraIntegration(integrationId, payload) {
  return requestJson(
    `/api/alertmanager/integrations/jira/${encodeURIComponent(integrationId)}`,
    { method: "PUT", payload },
  );
}
export async function deleteJiraIntegration(integrationId) {
  return request(
    `/api/alertmanager/integrations/jira/${encodeURIComponent(integrationId)}`,
    { method: "DELETE" },
  );
}
export async function createAlertRule(payload) {
  return requestJson("/api/alertmanager/rules", { payload });
}
export async function updateAlertRule(ruleId, payload) {
  return requestJson(`/api/alertmanager/rules/${encodeURIComponent(ruleId)}`, {
    method: "PUT",
    payload,
  });
}
export async function deleteAlertRule(ruleId) {
  return request(`/api/alertmanager/rules/${encodeURIComponent(ruleId)}`, {
    method: "DELETE",
  });
}
export async function testAlertRule(ruleId) {
  return request(`/api/alertmanager/rules/${encodeURIComponent(ruleId)}/test`, {
    method: "POST",
  });
}
export async function getNotificationChannels({ showHidden = false } = {}) {
  const params = new URLSearchParams();
  if (showHidden) params.set("show_hidden", "true");
  const qs = params.toString() ? `?${params.toString()}` : "";
  return request(`/api/alertmanager/channels${qs}`);
}
export async function setNotificationChannelHidden(channelId, hidden = true) {
  return requestJson(
    `/api/alertmanager/channels/${encodeURIComponent(channelId)}/hide`,
    { method: "POST", payload: { hidden: !!hidden } },
  );
}
export async function createNotificationChannel(payload) {
  return requestJson("/api/alertmanager/channels", { payload });
}
export async function updateNotificationChannel(channelId, payload) {
  return requestJson(
    `/api/alertmanager/channels/${encodeURIComponent(channelId)}`,
    {
      method: "PUT",
      payload,
    },
  );
}
export async function deleteNotificationChannel(channelId) {
  return request(
    `/api/alertmanager/channels/${encodeURIComponent(channelId)}`,
    {
      method: "DELETE",
    },
  );
}
export async function testNotificationChannel(channelId) {
  return request(
    `/api/alertmanager/channels/${encodeURIComponent(channelId)}/test`,
    {
      method: "POST",
    },
  );
}

export async function listMetricNames(orgId) {
  const params = new URLSearchParams();
  if (orgId) params.append("orgId", orgId);
  const qs = params.toString();
  const path = qs
    ? `/api/alertmanager/metrics/names?${qs}`
    : "/api/alertmanager/metrics/names";
  return request(path);
}

export async function queryLogs({
  query,
  limit = 100,
  start,
  end,
  direction = "backward",
  step,
}) {
  const params = new URLSearchParams();
  params.append("query", query);
  params.append("limit", limit.toString());
  if (start) params.append("start", start);
  if (end) params.append("end", end);
  if (direction) params.append("direction", direction);
  if (step) params.append("step", step);
  return request(`/api/loki/query?${params.toString()}`);
}
export async function getLabels() {
  return request("/api/loki/labels");
}
export async function getLabelValues(label, { query, start, end } = {}) {
  const params = new URLSearchParams();
  if (query) params.append("query", query);
  if (start) params.append("start", start);
  if (end) params.append("end", end);
  const queryString = params.toString();
  const suffix = queryString ? "?" + queryString : "";
  return request(
    `/api/loki/label/${encodeURIComponent(label)}/values${suffix}`,
  );
}
export async function searchLogs({ pattern, labels, start, end, limit = 100 }) {
  return requestJson("/api/loki/search", {
    payload: { pattern, labels, start, end, limit },
  });
}
export async function filterLogs({ labels, filters, start, end, limit = 100 }) {
  return requestJson("/api/loki/filter", {
    payload: { labels, filters, start, end, limit },
  });
}
export async function aggregateLogs(query, { start, end, step = 60 } = {}) {
  const params = new URLSearchParams();
  params.append("query", query);
  params.append("step", step.toString());
  if (start) params.append("start", start);
  if (end) params.append("end", end);
  return request(`/api/loki/aggregate?${params.toString()}`);
}
export async function getLogVolume(query, { start, end, step = 300 } = {}) {
  const params = new URLSearchParams();
  params.append("query", query);
  params.append("step", step.toString());
  if (start) params.append("start", start);
  if (end) params.append("end", end);
  return request(`/api/loki/volume?${params.toString()}`);
}

export async function searchTraces({
  service,
  operation,
  minDuration,
  maxDuration,
  start,
  end,
  limit = 100,
  fetchFull = false,
}) {
  const qs = [];
  if (service) qs.push(`service=${encodeURIComponent(service)}`);
  if (operation) qs.push(`operation=${encodeURIComponent(operation)}`);
  if (minDuration) qs.push(`minDuration=${encodeURIComponent(minDuration)}`);
  if (maxDuration) qs.push(`maxDuration=${encodeURIComponent(maxDuration)}`);
  if (start) qs.push(`start=${start}`);
  if (end) qs.push(`end=${end}`);
  qs.push(`limit=${limit}`);
  qs.push(`fetchFull=${fetchFull ? "true" : "false"}`);
  return request(`/api/tempo/traces/search?${qs.join("&")}`);
}
export async function fetchTempoServices() {
  return request("/api/tempo/services");
}
export async function getTrace(traceID) {
  return request(`/api/tempo/traces/${encodeURIComponent(traceID)}`);
}

export async function createRcaAnalyzeJob(payload) {
  return requestJson("/api/becertain/analyze/jobs", { payload });
}

export async function listRcaJobs(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && `${value}` !== "") {
      search.set(key, String(value));
    }
  });
  const qs = search.toString();
  return request(`/api/becertain/analyze/jobs${qs ? `?${qs}` : ""}`);
}

export async function getRcaJob(jobId) {
  return request(`/api/becertain/analyze/jobs/${encodeURIComponent(jobId)}`);
}

export async function getRcaJobResult(jobId) {
  return request(
    `/api/becertain/analyze/jobs/${encodeURIComponent(jobId)}/result`,
  );
}

export async function getRcaReportById(reportId) {
  return request(`/api/becertain/reports/${encodeURIComponent(reportId)}`);
}

export async function deleteRcaReport(reportId) {
  return request(`/api/becertain/reports/${encodeURIComponent(reportId)}`, {
    method: "DELETE",
  });
}

export async function fetchRcaMetricAnomalies(payload) {
  return requestJson("/api/becertain/anomalies/metrics", { payload });
}

export async function fetchRcaLogPatterns(payload) {
  return requestJson("/api/becertain/anomalies/logs/patterns", { payload });
}

export async function fetchRcaLogBursts(payload) {
  return requestJson("/api/becertain/anomalies/logs/bursts", { payload });
}

export async function fetchRcaTraceAnomalies(payload) {
  return requestJson("/api/becertain/anomalies/traces", { payload });
}

export async function fetchRcaCorrelate(payload) {
  return requestJson("/api/becertain/correlate", { payload });
}

export async function fetchRcaTopology(payload) {
  return requestJson("/api/becertain/topology/blast-radius", { payload });
}

export async function fetchRcaSloBurn(payload) {
  return requestJson("/api/becertain/slo/burn", { payload });
}

export async function fetchRcaForecast(payload, params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && `${value}` !== "") {
      search.set(key, String(value));
    }
  });
  const qs = search.toString();
  return requestJson(
    `/api/becertain/forecast/trajectory${qs ? `?${qs}` : ""}`,
    { payload },
  );
}

export async function fetchRcaGranger(payload, params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && `${value}` !== "") {
      search.set(key, String(value));
    }
  });
  const qs = search.toString();
  return requestJson(`/api/becertain/causal/granger${qs ? `?${qs}` : ""}`, {
    payload,
  });
}

export async function fetchRcaBayesian(payload) {
  return requestJson("/api/becertain/causal/bayesian", { payload });
}

export async function getRcaMlWeights() {
  return request("/api/becertain/ml/weights");
}

export async function getRcaDeployments() {
  return request("/api/becertain/events/deployments");
}

export async function searchDashboards({
  query = "",
  uid,
  labelKey,
  labelValue,
  teamId,
  showHidden = false,
  tag,
  starred,
} = {}) {
  const params = new URLSearchParams();
  if (query) params.append("query", query);
  if (uid) params.append("uid", uid);
  if (labelKey) params.append("label_key", labelKey);
  if (labelValue) params.append("label_value", labelValue);
  if (teamId) params.append("team_id", teamId);
  if (showHidden) params.append("show_hidden", "true");
  if (tag) params.append("tag", tag);
  if (starred !== undefined && starred !== null)
    params.append("starred", starred);
  const qs = params.toString();
  return request(
    qs
      ? `/api/grafana/dashboards/search?${qs}`
      : "/api/grafana/dashboards/search",
  );
}
export async function getDashboard(uid) {
  return request(`/api/grafana/dashboards/${encodeURIComponent(uid)}`);
}
export async function createGrafanaBootstrapSession(nextPath = "/dashboards") {
  return requestJson("/api/grafana/bootstrap-session", {
    payload: { next: nextPath },
  });
}
export async function createDashboard(payload, queryParams = "") {
  const url = queryParams
    ? `/api/grafana/dashboards?${queryParams}`
    : "/api/grafana/dashboards";
  return requestJson(url, { payload });
}
export async function updateDashboard(uid, payload, queryParams = "") {
  const url = queryParams
    ? `/api/grafana/dashboards/${encodeURIComponent(uid)}?${queryParams}`
    : `/api/grafana/dashboards/${encodeURIComponent(uid)}`;
  return requestJson(url, { method: "PUT", payload });
}
export async function deleteDashboard(uid) {
  return request(`/api/grafana/dashboards/${encodeURIComponent(uid)}`, {
    method: "DELETE",
  });
}
export async function toggleDashboardHidden(uid, hidden = true) {
  return requestJson(
    `/api/grafana/dashboards/${encodeURIComponent(uid)}/hide`,
    {
      payload: { hidden },
    },
  );
}
export async function getDashboardFilterMeta() {
  return request("/api/grafana/dashboards/meta/filters");
}

export async function getDatasources({
  uid,
  labelKey,
  labelValue,
  teamId,
  showHidden = false,
} = {}) {
  const params = new URLSearchParams();
  if (uid) params.append("uid", uid);
  if (labelKey) params.append("label_key", labelKey);
  if (labelValue) params.append("label_value", labelValue);
  if (teamId) params.append("team_id", teamId);
  if (showHidden) params.append("show_hidden", "true");
  const qs = params.toString();
  return request(
    qs ? `/api/grafana/datasources?${qs}` : "/api/grafana/datasources",
  );
}
export async function getDatasource(uid) {
  return request(`/api/grafana/datasources/uid/${encodeURIComponent(uid)}`);
}
export async function createDatasource(payload, queryParams = "") {
  const url = queryParams
    ? `/api/grafana/datasources?${queryParams}`
    : "/api/grafana/datasources";
  return requestJson(url, { payload });
}
export async function updateDatasource(uid, payload, queryParams = "") {
  const url = queryParams
    ? `/api/grafana/datasources/${encodeURIComponent(uid)}?${queryParams}`
    : `/api/grafana/datasources/${encodeURIComponent(uid)}`;
  return requestJson(url, { method: "PUT", payload });
}
export async function deleteDatasource(uid) {
  return request(`/api/grafana/datasources/${encodeURIComponent(uid)}`, {
    method: "DELETE",
  });
}
export async function toggleDatasourceHidden(uid, hidden = true) {
  return requestJson(
    `/api/grafana/datasources/${encodeURIComponent(uid)}/hide`,
    {
      payload: { hidden },
    },
  );
}
export async function getDatasourceFilterMeta() {
  return request("/api/grafana/datasources/meta/filters");
}

export async function getFolders() {
  return request("/api/grafana/folders");
}
export async function createFolder(title) {
  return requestJson("/api/grafana/folders", { payload: { title } });
}
export async function deleteFolder(uid) {
  return request(`/api/grafana/folders/${encodeURIComponent(uid)}`, {
    method: "DELETE",
  });
}

export default { fetchInfo };
