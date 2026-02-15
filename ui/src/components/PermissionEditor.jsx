import { useState, useEffect, useMemo } from 'react'
import PropTypes from 'prop-types'
import { Button, Card, Badge, Spinner, Modal } from './ui'
import { useToast } from '../contexts/ToastContext'
import HelpTooltip from './HelpTooltip'
import * as api from '../api'

export default function PermissionEditor({ user, groups, onClose, onSave }) {
  const toast = useToast();
  const [saving, setSaving] = useState(false)
  const [loadingPermissions, setLoadingPermissions] = useState(true)
  const [permissionsList, setPermissionsList] = useState([])
  const [permissionsByCategory, setPermissionsByCategory] = useState({})
  const [roleDefaults, setRoleDefaults] = useState({})
  const [selectedPermissions, setSelectedPermissions] = useState(new Set())
  const [selectedGroups, setSelectedGroups] = useState(new Set(user.group_ids || []))
  const [role, setRole] = useState(user.role)
  const [expandedGroups, setExpandedGroups] = useState(new Set())
  const [computedPermissions, setComputedPermissions] = useState(new Set())

  const roleBadgeVariant = useMemo(() => {
    if (role === 'admin') return 'error'
    if (role === 'user') return 'info'
    return 'default'
  }, [role])

  const getCategoryDescription = (category) => {
    const descriptions = {
      agents: 'Granular OTEL agent access by action (read/create/update/delete/test).',
      alerts: 'Granular alert and silence access by action (read/create/update/delete).',
      channels: 'Granular notification channel access (read/create/update/delete/test).',
      dashboards: 'Granular dashboard access (read/create/update/delete).',
      datasources: 'Granular datasource access (read/query/create/update/delete).',
      folders: 'Granular Grafana folder access (read/create/delete).',
      groups: 'Granular group access (read/create/update/delete).',
      logs: 'Read/query Loki logs.',
      rules: 'Granular alert rule access (read/create/update/delete/test).',
      tenants: 'Tenant administration permissions.',
      traces: 'Read/query Tempo traces.',
      users: 'Granular user access (read/create/update/delete).'
    }
    return descriptions[category] || `Granular ${category} permissions by action (read/create/update/delete/test).`
  }

  const getPermissionDescription = (permissionName) => {
    const descriptions = {
      'Read Agents': 'View OTEL agents and system metrics',
      'View OTEL agents and system metrics': 'View OTEL agents and system metrics',
      'Delete Alerts': 'Delete alert rules and active alerts',
      'Delete alert rules': 'Delete alert rules and active alerts',
      'Read Alerts': 'View alert rules and active alerts',
      'View alert rules and active alerts': 'View alert rules and active alerts',
      'Write Alerts': 'Create and update alert rules',
      'Create and update alert rules': 'Create and update alert rules',
      'Delete Channels': 'Delete notification channels',
      'Delete notification channels': 'Delete notification channels',
      'Read Channels': 'View notification channels',
      'View notification channels': 'View notification channels',
      'Write Channels': 'Create and update notification channels',
      'Create and update notification channels': 'Create and update notification channels',
      'Delete Dashboards': 'Delete Grafana dashboards',
      'Delete dashboards': 'Delete Grafana dashboards',
      'Read Dashboards': 'View Grafana dashboards',
      'View Grafana dashboards': 'View Grafana dashboards',
      'Write Dashboards': 'Create and update Grafana dashboards',
      'Create and update dashboards': 'Create and update Grafana dashboards',
      'Manage Groups': 'Create, update, and delete user groups',
      'Create, update, and delete groups': 'Create, update, and delete user groups',
      'Read Groups': 'View group information and membership',
      'View group information': 'View group information and membership',
      'Read Logs': 'Query and view application logs',
      'Query and view logs': 'Query and view application logs',
      'Manage Tenants': 'Manage tenant settings and configurations',
      'Manage tenant settings': 'Manage tenant settings and configurations',
      'Read Traces': 'Query and view distributed traces',
      'Query and view traces': 'Query and view distributed traces',
      'Manage Users': 'Create, update, and delete user accounts',
      'Create, update, and delete users': 'Create, update, and delete user accounts',
      'Read Users': 'View user information and accounts',
      'View user information': 'View user information and accounts'
    }
    if (descriptions[permissionName]) return descriptions[permissionName]

    const normalized = String(permissionName || '').toLowerCase()
    if (normalized.includes(':')) {
      const [action, resource] = normalized.split(':')
      const readableResource = (resource || 'resource').replace(/_/g, ' ')
      const readableAction = action || 'manage'
      return `${readableAction.charAt(0).toUpperCase()}${readableAction.slice(1)} ${readableResource}`
    }

    return permissionName
  }

  const allPermissionNames = useMemo(
    () => permissionsList.map((p) => p.name || p.id).filter(Boolean),
    [permissionsList]
  )

  const getRoleDefaults = (roleName) => {
    if (roleDefaults?.[roleName]?.length) return roleDefaults[roleName]
    if (roleName === 'admin') return allPermissionNames
    return []
  }

  useEffect(() => {
    const loadPermissions = async () => {
      try {
        setLoadingPermissions(true)
        const [perms, defaults] = await Promise.all([
          api.getPermissions(),
          api.getRoleDefaults()
        ])
        const permissions = Array.isArray(perms) ? perms : []
        const grouped = permissions.reduce((acc, perm) => {
          const key = perm.resource_type || 'general'
          if (!acc[key]) acc[key] = []
          acc[key].push(perm)
          return acc
        }, {})
        setPermissionsList(permissions)
        setPermissionsByCategory(grouped)
        setRoleDefaults(defaults || {})
      } catch (error) {
        toast.error('Failed to load permissions')
      } finally {
        setLoadingPermissions(false)
      }
    }

    loadPermissions()
  }, [toast])

  useEffect(() => {
    // Initialize editable state from the user payload
    const hasDirectPermissions = Object.hasOwn(user, 'direct_permissions')
    const directPermsSource = hasDirectPermissions ? (user.direct_permissions || []) : []
    const directPerms = directPermsSource.map(p => (typeof p === 'string' ? p : p.name))
    setSelectedPermissions(new Set(directPerms))
    setSelectedGroups(new Set(user.group_ids || []))
    setRole(user.role)
  }, [user])

  useEffect(() => {
    // Compute all permissions (role + group + direct) for display
    const rolePerms = getRoleDefaults(role)
    const groupPerms = new Set()
    ;(selectedGroups || []).forEach(gid => {
      const group = groups.find(g => g.id === gid)
      if (group?.permissions) {
        group.permissions.forEach(p => {
          const pname = typeof p === 'string' ? p : (p.name || p.id)
          groupPerms.add(pname)
        })
      }
    })
    const allPerms = new Set([...rolePerms, ...groupPerms, ...selectedPermissions])
    setComputedPermissions(allPerms)
  }, [role, selectedGroups, selectedPermissions, groups, roleDefaults, permissionsList])

  const handleRoleChange = (newRole) => {
    setRole(newRole)
  }

  const togglePermission = (permId) => {
    const newPerms = new Set(selectedPermissions)
    if (newPerms.has(permId)) {
      newPerms.delete(permId)
    } else {
      newPerms.add(permId)
    }
    setSelectedPermissions(newPerms)
  }

  const toggleGroup = (groupId) => {
    const newGroups = new Set(selectedGroups)
    if (newGroups.has(groupId)) {
      newGroups.delete(groupId)
    } else {
      newGroups.add(groupId)
    }
    setSelectedGroups(newGroups)
  }

  const toggleExpanded = (groupId) => {
    const next = new Set(expandedGroups)
    if (next.has(groupId)) next.delete(groupId)
    else next.add(groupId)
    setExpandedGroups(next)
  }

  const selectAllInCategory = (category) => {
    const categoryPerms = (permissionsByCategory[category] || []).map((p) => p.name || p.id)
    const newPerms = new Set(selectedPermissions)
    categoryPerms.forEach(p => newPerms.add(p))
    setSelectedPermissions(newPerms)
  }

  const deselectAllInCategory = (category) => {
    const categoryPerms = (permissionsByCategory[category] || []).map((p) => p.name || p.id)
    const newPerms = new Set(selectedPermissions)
    categoryPerms.forEach(p => newPerms.delete(p))
    setSelectedPermissions(newPerms)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      // Update user role and groups
      await onSave({
        role,
        group_ids: Array.from(selectedGroups)
      })
      
      // Update user permissions (direct permissions override group/role)
      await api.updateUserPermissions(user.id, Array.from(selectedPermissions))
      
      toast.success('Permissions saved successfully');
      onClose();
    } catch (error) {
      toast.error('Error saving: ' + error.message);
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      isOpen
      onClose={onClose}
      closeOnOverlayClick={false}
      title={`Edit User: ${user.username}`}
      size="xl"
      footer={
        <div className="flex gap-3 justify-end">
          <Button onClick={onClose} variant="ghost">
            Cancel
          </Button>
          <Button onClick={handleSave} variant="primary" disabled={saving}>
            {saving ? <Spinner size="sm" /> : 'Save Changes'}
          </Button>
        </div>
      }
    >
      <div className="space-y-6">
        <div>
          <p className="text-sre-text-muted">
            Configure role, groups, and direct access permissions.
          </p>
        </div>

        <div className="space-y-6 overflow-y-auto pr-1">
          {/* Role Selection */}
          <div className="flex items-start gap-2">
            <div className="flex-1">
              <label htmlFor='role' className="block text-sm font-semibold text-sre-text mb-2">Role</label>
              <select
                id='role'
                value={role}
                onChange={(e) => handleRoleChange(e.target.value)}
                className="w-full px-3 pr-10 py-2 bg-sre-bg-alt border border-sre-border rounded text-sre-text"
              >
                <option value="viewer">Viewer - Read-only access</option>
                <option value="user">User - Read and write access</option>
                <option value="admin">Admin - Full access</option>
              </select>
            </div>
            <HelpTooltip text="Roles provide baseline access. Direct and group permissions then add granular action-level rights (for example create, update, delete, test)." />
          </div>

          {/* Group Membership */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <label htmlFor='group' className="block text-sm font-semibold text-sre-text">
                Group Membership
              </label>
              <HelpTooltip text="Groups provide additional permissions beyond the user's role. Users inherit all permissions from their assigned groups." />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {groups.map((group) => (
                <div key={group.id} className="">
                  <div className="flex items-start gap-3 p-3 bg-sre-bg-alt border border-sre-border rounded-lg">
                    <div className="flex-shrink-0 pt-1">
                      <input
                        id={`group-${group.id}`}
                        type="checkbox"
                        checked={selectedGroups.has(group.id)}
                        onChange={() => toggleGroup(group.id)}
                        className="w-5 h-5"
                      />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="font-medium text-sre-text truncate">{group.name}</div>
                          <Badge variant="secondary" className="text-xs px-2 py-0.5">{(group.permissions || []).length} perm{(group.permissions || []).length === 1 ? '' : 's'}</Badge>
                        </div>
                        <button
                          type="button"
                          onClick={() => toggleExpanded(group.id)}
                          aria-expanded={expandedGroups.has(group.id)}
                          className="ml-3 text-sre-text-muted hover:text-sre-text p-1 rounded-md"
                        >
                          <svg className={"w-4 h-4 transform transition-transform " + (expandedGroups.has(group.id) ? 'rotate-180' : '')} viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 011.08 1.04l-4.25 4.25a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z" clipRule="evenodd" />
                          </svg>
                        </button>
                      </div>
                      {group.description && (
                        <div className="text-xs text-sre-text-muted mt-1 truncate" title={group.description}>{group.description}</div>
                      )}
                    </div>
                  </div>

                  {expandedGroups.has(group.id) && (
                    <Card className="!p-4 ml-6 mt-3 rounded-lg border border-sre-border">
                      <div className="flex items-center justify-between mb-3">
                        <div className="text-sm font-semibold text-sre-text">Group Permissions</div>
                        <div className="text-xs text-sre-text-muted">{(group.permissions || []).length} permissions</div>
                      </div>

                      {(group.permissions || []).length === 0 ? (
                        <div className="text-xs text-sre-text-muted">No explicit permissions on this group</div>
                      ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          {(group.permissions || []).map((perm) => {
                            const permName = typeof perm === 'string' ? perm : (perm.display_name || perm.name || perm.id)
                            const permDesc = typeof perm === 'string' ? '' : (perm.description || getPermissionDescription(permName))
                            const key = typeof perm === 'string' ? perm : perm.id
                            return (
                              <div key={key} className="p-3 bg-sre-bg-alt border border-sre-border rounded-lg">
                                <div className="font-medium text-sm text-sre-text truncate">{permName}</div>
                                {permDesc && <div className="text-xs text-sre-text-muted mt-1 line-clamp-2">{permDesc}</div>}
                              </div>
                            )
                          })}
                        </div>
                      )}
                    </Card>
                  )}
                </div>
              ))}
              {groups.length === 0 && (
                <div className="col-span-2 text-center py-4 text-sre-text-muted">
                  No groups available
                </div>
              )}
            </div>
          </div>

          {/* Permissions by Category */}
          <div>
            <div className="flex items-center gap-2 mt-4 mb-3">
              <label htmlFor="direct-permissions" className="block text-sm font-semibold text-sre-text">
                Direct Permissions (additive to role and group access)
              </label>
              <HelpTooltip text="Direct permissions are additive to role and group access, and are best used for targeted action-level exceptions." />
            </div>
            <div id="direct-permissions" className="space-y-4">
              {loadingPermissions && (
                <div className="flex items-center gap-2 text-sre-text-muted">
                  <Spinner size="sm" /> Loading permissions...
                </div>
              )}
              {!loadingPermissions && Object.entries(permissionsByCategory).map(([category, perms]) => {
                const allSelected = perms.every(p => selectedPermissions.has(p.name || p.id))
                const someSelected = perms.some(p => selectedPermissions.has(p.name || p.id))

                return (
                  <Card key={category} className="!p-4">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-sre-text capitalize">
                          {category}
                        </h3>
                        <HelpTooltip text={getCategoryDescription(category)} />
                      </div>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => selectAllInCategory(category)}
                          disabled={allSelected}
                        >
                          Select All
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => deselectAllInCategory(category)}
                          disabled={!someSelected}
                        >
                          Clear All
                        </Button>
                      </div>
                    </div>
                    <div className="space-y-2">
                      {perms.map((perm) => {
                        const permName = perm.name || perm.id
                        const displayName = perm.display_name || perm.name || perm.id
                        const description = perm.description || perm.name || ''
                        const isDirectlySet = selectedPermissions.has(permName)
                        const isFromRoleOrGroup = computedPermissions.has(permName) && !isDirectlySet
                        const isChecked = computedPermissions.has(permName)
                        return (
                          <label
                            key={permName} 
                            htmlFor={`perm-${permName}`}
                            className="flex items-start gap-3 p-2 rounded hover:bg-sre-accent/5 cursor-pointer"
                          >
                            <input
                              type="checkbox"
                              id={`perm-${permName}`}
                              checked={isChecked}
                              onChange={() => togglePermission(permName)}
                              className="w-4 h-4 mt-0.5"
                              aria-label={displayName}
                            />
                            <div className="flex-1">
                              <div className="font-medium text-sre-text text-sm flex items-center gap-2">
                                {displayName}
                                {isFromRoleOrGroup && (
                                  <span className="text-xs px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400">from role/group</span>
                                )}
                                <HelpTooltip text={getPermissionDescription(displayName)} />
                              </div>
                              <div className="text-xs text-sre-text-muted">
                                {description}
                              </div>
                            </div>
                          </label>
                        )
                      })}
                    </div>
                  </Card>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </Modal>
  )
}

PermissionEditor.propTypes = {
  user: PropTypes.object.isRequired,
  groups: PropTypes.array.isRequired,
  onClose: PropTypes.func.isRequired,
  onSave: PropTypes.func.isRequired
}
