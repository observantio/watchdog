`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

export function shouldIgnoreAlertManagerError(error) {
  if (!error) return true
  if (error.status === 403) return true
  if (error.message?.includes('Error sending test notification')) return true
  return false
}

export function normalizeRuleForUI(rule) {
  if (!rule) return rule
  return {
    ...rule,
    orgId: rule.orgId || rule.org_id || undefined,
    expr: rule.expr || rule.expression || '',
    duration: rule.duration || rule.for || rule['for'] || undefined,
    group: rule.group || rule.groupName || rule.group_name || 'default',
    groupInterval: rule.groupInterval || rule.group_interval || undefined,
    notificationChannels: rule.notificationChannels || rule.notification_channels || [],
    sharedGroupIds: rule.sharedGroupIds || rule.shared_group_ids || [],
    annotations: rule.annotations || {},
    labels: rule.labels || {},
  }
}

export function buildRulePayload(ruleData) {
  return {
    name: ruleData.name,
    orgId: ruleData.orgId || ruleData.org_id || undefined,
    expression: ruleData.expr || ruleData.expression || '',
    severity: ruleData.severity,
    description: ruleData.annotations?.description || ruleData.description || '',
    annotations: ruleData.annotations || {},
    for: ruleData.duration || ruleData.for || undefined,
    groupName: ruleData.group || ruleData.groupName || 'default',
    groupInterval: ruleData.groupInterval || ruleData.group_interval || undefined,
    enabled: typeof ruleData.enabled === 'boolean' ? ruleData.enabled : true,
    labels: ruleData.labels || {},
    notificationChannels: ruleData.notificationChannels || ruleData.notification_channels || [],
    visibility: ruleData.visibility || 'private',
    sharedGroupIds: ruleData.sharedGroupIds || ruleData.shared_group_ids || [],
  }
}