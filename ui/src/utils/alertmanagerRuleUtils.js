
export function normalizeRuleOrgId(value) {
  const normalized = String(value || "").trim();
  if (!normalized) return undefined;
  if (normalized.toLowerCase() === "default") return undefined;
  return normalized;
}

export function normalizeRuleForUI(rule) {
  if (!rule) return rule;
  return {
    ...rule,
    orgId: normalizeRuleOrgId(rule.orgId || rule.org_id),
    expr: rule.expr || rule.expression || "",
    duration: rule.duration || rule.for || rule["for"] || undefined,
    group: rule.group || rule.groupName || rule.group_name || "default",
    groupInterval: rule.groupInterval || rule.group_interval || undefined,
    notificationChannels:
      rule.notificationChannels || rule.notification_channels || [],
    sharedGroupIds: rule.sharedGroupIds || rule.shared_group_ids || [],
    annotations: rule.annotations || {},
    labels: rule.labels || {},
  };
}

export function buildRulePayload(ruleData) {
  return {
    name: ruleData.name,
    orgId: normalizeRuleOrgId(ruleData.orgId || ruleData.org_id),
    expression: ruleData.expr || ruleData.expression || "",
    severity: ruleData.severity,
    description:
      ruleData.annotations?.description || ruleData.description || "",
    annotations: ruleData.annotations || {},
    for: ruleData.duration || ruleData.for || undefined,
    groupName: ruleData.group || ruleData.groupName || "default",
    groupInterval:
      ruleData.groupInterval || ruleData.group_interval || undefined,
    enabled: typeof ruleData.enabled === "boolean" ? ruleData.enabled : true,
    labels: ruleData.labels || {},
    notificationChannels:
      ruleData.notificationChannels || ruleData.notification_channels || [],
    visibility: ruleData.visibility || "private",
    sharedGroupIds: ruleData.sharedGroupIds || ruleData.shared_group_ids || [],
  };
}
