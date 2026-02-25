const CATEGORY_DESCRIPTIONS = {
  agents: 'Granular OTEL agent permissions (read/create/update/delete/test).',
  alerts: 'Granular alert and silence permissions (read/create/update/delete).',
  channels: 'Granular notification channel permissions (read/create/update/delete/test).',
  dashboards: 'Granular dashboard access (read/create/update/delete).',
  datasources: 'Granular datasource access (read/query/create/update/delete).',
  folders: 'Granular Grafana folder permissions (read/create/delete).',
  groups: 'Granular group permissions (read/create/update/delete).',
  logs: 'Read/query Loki logs.',
  rules: 'Granular alert rule permissions (read/create/update/delete/test).',
  tenants: 'Tenant administration permissions.',
  traces: 'Read/query Tempo traces.',
  users: 'Granular user permissions (read/create/update/delete).',
}

export function getCategoryDescription(category) {
  return CATEGORY_DESCRIPTIONS[category] || `Granular ${category} permissions by action (read/create/update/delete/test).`
}

export function groupPermissionsByResource(permissions) {
  return (permissions || []).reduce((grouped, permission) => {
    const resourceType = permission.resource_type || 'general'
    if (!grouped[resourceType]) grouped[resourceType] = []
    grouped[resourceType].push(permission)
    return grouped
  }, {})
}

export function filterGroups(groups, query) {
  const normalizedQuery = (query || '').toLowerCase()
  return (groups || []).filter((group) => (
    !normalizedQuery
      || group.name?.toLowerCase().includes(normalizedQuery)
      || group.description?.toLowerCase().includes(normalizedQuery)
  ))
}

export function sortUsersByDisplayName(users) {
  return (users || []).slice().sort((a, b) => {
    const nameA = (a.full_name || a.username || '').toLowerCase()
    const nameB = (b.full_name || b.username || '').toLowerCase()
    return nameA.localeCompare(nameB)
  })
}