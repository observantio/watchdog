import { useState, useEffect, useMemo } from 'react'
import PropTypes from 'prop-types'
import { Button, Card, Badge, Spinner, Modal } from './ui'
import { useToast } from '../contexts/ToastContext'
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
        console.error('Failed to load permissions:', error)
      } finally {
        setLoadingPermissions(false)
      }
    }

    loadPermissions()
  }, [toast])

  useEffect(() => {
    // Direct permissions are what we edit
    const hasDirectPermissions = Object.hasOwn(user, 'direct_permissions')
    const directPermsSource = hasDirectPermissions ? (user.direct_permissions || []) : []
    const directPerms = directPermsSource.map(p => (typeof p === 'string' ? p : p.name))
    setSelectedPermissions(new Set(directPerms))

    // Compute all permissions (role + group + direct) for display
    const rolePerms = getRoleDefaults(user.role)
    const groupPerms = new Set()
    ;(user.group_ids || []).forEach(gid => {
      const group = groups.find(g => g.id === gid)
      if (group?.permissions) {
        group.permissions.forEach(p => {
          const pname = typeof p === 'string' ? p : (p.name || p.id)
          groupPerms.add(pname)
        })
      }
    })
    
    const allPerms = new Set([...rolePerms, ...groupPerms, ...directPerms])
    setComputedPermissions(allPerms)
  }, [user, groups, roleDefaults, permissionsList])

  const handleRoleChange = (newRole) => {
    setRole(newRole)
    // Don't automatically clear direct permissions when role changes
    // Just update computed permissions for display
    const rolePerms = getRoleDefaults(newRole)
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
  }

  const togglePermission = (permId) => {
    const newPerms = new Set(selectedPermissions)
    if (newPerms.has(permId)) {
      newPerms.delete(permId)
    } else {
      newPerms.add(permId)
    }
    setSelectedPermissions(newPerms)

    // Recompute computedPermissions so UI (checkbox checked state) updates immediately
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
    const allPerms = new Set([...rolePerms, ...groupPerms, ...newPerms])
    setComputedPermissions(allPerms)
  }

  const toggleGroup = (groupId) => {
    const newGroups = new Set(selectedGroups)
    if (newGroups.has(groupId)) {
      newGroups.delete(groupId)
    } else {
      newGroups.add(groupId)
    }
    setSelectedGroups(newGroups)
    
    // Recompute permissions when groups change
    const rolePerms = getRoleDefaults(role)
    const groupPerms = new Set()
    newGroups.forEach(gid => {
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
      console.error('Save error:', error);
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      isOpen
      onClose={onClose}
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
          <div>
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

          {/* Group Membership */}
          <div>
            <label htmlFor='group' className="block text-sm font-semibold text-sre-text mb-2">
              Group Membership
            </label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {groups.map((group) => (
                <div key={group.id} className="space-y-2">
                  <div className="flex items-center gap-2 p-3 bg-sre-bg-alt border border-sre-border rounded">
                    <input
                      id={`group-${group.id}`}
                      type="checkbox"
                      checked={selectedGroups.has(group.id)}
                      onChange={() => toggleGroup(group.id)}
                      className="w-4 h-4"
                    />
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <div className="font-medium text-sre-text">{group.name}</div>
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
                        <div className="text-xs text-sre-text-muted">{group.description}</div>
                      )}
                    </div>
                  </div>

                  {expandedGroups.has(group.id) && (
                    <Card className="!p-3 ml-6">
                      <div className="text-sm font-semibold text-sre-text mb-2">Group Permissions</div>
                      <div className="space-y-2">
                        {(group.permissions || []).length === 0 && (
                          <div className="text-xs text-sre-text-muted">No explicit permissions on this group</div>
                        )}
                        {(group.permissions || []).map((perm) => {
                          const name = typeof perm === 'string' ? perm : (perm.display_name || perm.name || perm.id)
                          const desc = typeof perm === 'string' ? '' : (perm.description || '')
                          return (
                            <div key={typeof perm === 'string' ? perm : perm.id} className="flex items-start gap-3">
                              <div className="text-sm font-medium text-sre-text">{name}</div>
                              {desc && <div className="text-xs text-sre-text-muted">{desc}</div>}
                            </div>
                          )
                        })}
                      </div>
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
            <label htmlFor="direct-permissions" className="block text-sm mt-4 font-semibold text-sre-text mb-3">
              Direct Permissions (additive to role and group access)
            </label>
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
                      <h3 className="font-semibold text-sre-text capitalize">
                        {category}
                      </h3>
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
                          Clear
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

          {/* Summary */}
          <div className="p-4 bg-sre-accent/10 border border-sre-accent/30 rounded">
            <div className="text-sm font-semibold text-sre-text mb-2">Summary</div>
            <div className="text-sm text-sre-text-muted space-y-1">
              <div>Role: <Badge variant={roleBadgeVariant}>{role}</Badge></div>
              <div>Groups: {selectedGroups.size} selected</div>
              <div>Permissions: {selectedPermissions.size} enabled</div>
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
