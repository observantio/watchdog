/**
 * Groups Management Page
 * Manage groups and assign permissions with least privilege enforcement
*/

import { useState, useEffect } from 'react';
import { Card, Button, Input, Textarea, Modal, ConfirmDialog, Badge, Alert, Checkbox } from '../components/ui';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../hooks/usePermissions';
import { useToast } from '../contexts/ToastContext';
import HelpTooltip from '../components/HelpTooltip';
import * as api from '../api';

/**
 * Reusable member list for group modals (Create, Edit, Permissions)
 */
function MemberList({ users, selectedMembers, toggleMember }) {
  const [searchQuery, setSearchQuery] = useState('');
  
  if (!users.length) {
    return <div className="text-sm text-sre-text-muted">No users available.</div>
  }

  // Filter users based on search query
  const filteredUsers = users.filter(user => {
    const query = searchQuery.toLowerCase();
    return (
      (user.full_name || user.username).toLowerCase().includes(query) ||
      user.email.toLowerCase().includes(query)
    );
  });

  // Limit to 5 users
  const displayedUsers = filteredUsers.slice(0, 5);
  const hasMore = filteredUsers.length > 5;

  return (
    <div className="space-y-3">
      <Input
        placeholder="Search users by name or email..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        className="text-sm"
      />
      
      <div className="max-h-64 overflow-y-auto space-y-2 pr-2">
        {displayedUsers.length === 0 ? (
          <div className="text-sm text-sre-text-muted">
            {searchQuery ? 'No users match your search.' : 'No users available.'}
          </div>
        ) : (
          <>
            {displayedUsers.map((user) => (
              <label key={user.id} className="flex items-center gap-3 p-2 border border-sre-border rounded hover:bg-sre-surface/50 cursor-pointer">
                <Checkbox
                  checked={selectedMembers.includes(user.id)}
                  onChange={() => toggleMember(user.id)}
                />
                <div className="text-sm text-sre-text">
                  {user.full_name || user.username}
                  <span className="text-xs text-sre-text-muted ml-2">{user.email}</span>
                </div>
              </label>
            ))}
            {hasMore && (
              <div className="text-xs text-sre-text-muted text-center py-2">
                Showing first 5 of {filteredUsers.length} users. Use search to find specific users.
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default function GroupsPage() {
  const { canManageGroups } = usePermissions();
  const toast = useToast();
  const navigate = useNavigate();
  const [groups, setGroups] = useState([]);
  const [users, setUsers] = useState([]);
  const [permissions, setPermissions] = useState([]);
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [saving, setSaving] = useState(false);
  
  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showPermissionsModal, setShowPermissionsModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  
  // Form states
  const [formData, setFormData] = useState({ name: '', description: '' });
  const [editGroupData, setEditGroupData] = useState({ id: '', name: '', description: '' });
  const [groupPermissions, setGroupPermissions] = useState([]);
  const [selectedMembers, setSelectedMembers] = useState([]);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [groupsData, permsData] = await Promise.all([
        api.getGroups(),
        api.getPermissions()
      ]);
      setGroups(groupsData);
      setPermissions(permsData);
      const usersData = await api.getUsers().catch(() => []);
      setUsers(usersData || []);
    } catch (err) {
      toast.error('Failed to load groups: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const createGroup = async () => {
    if (!formData.name.trim()) {
      toast.error('Group name is required');
      return;
    }
    
    setSaving(true);
    try {
      // Create the group first
      const newGroup = await api.createGroup(formData);
      
      // If permissions are selected, update them
      if (groupPermissions?.length > 0) {
        await api.updateGroupPermissions(newGroup.id, groupPermissions);
      }
      await api.updateGroupMembers(newGroup.id, selectedMembers);
      
      toast.success('Group created successfully');
      setShowCreateModal(false);
      setFormData({ name: '', description: '' });
      setGroupPermissions([]);
      setSelectedMembers([]);
      await fetchData();
    } catch (err) {
      toast.error('Failed to create group: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  const deleteGroup = async (groupId) => {
    try {
      await api.deleteGroup(groupId);
      toast.success('Group deleted successfully');
      fetchData();
    } catch (err) {
      toast.error('Failed to delete group: ' + err.message);
    }
  };

  const openPermissionsModal = (group) => {
    setSelectedGroup(group);
    // Set current group permissions
    const currentPerms = group.permissions?.map(p => p.name || p) || [];
    setGroupPermissions(currentPerms);
    const memberIds = (users || []).filter(u => (u.group_ids || []).includes(group.id)).map(u => u.id);
    setSelectedMembers(memberIds);
    setShowPermissionsModal(true);
  };

  const openEditModal = (group) => {
    setEditGroupData({
      id: group.id,
      name: group.name || '',
      description: group.description || ''
    });
    const memberIds = (users || []).filter(u => (u.group_ids || []).includes(group.id)).map(u => u.id);
    setSelectedMembers(memberIds);
    setShowEditModal(true);
  };

  const savePermissions = async () => {
    setSaving(true);
    try {
      await api.updateGroupPermissions(selectedGroup.id, groupPermissions);
      await api.updateGroupMembers(selectedGroup.id, selectedMembers);
      toast.success('Permissions updated successfully');
      setShowPermissionsModal(false);
      setSelectedGroup(null);
      setSelectedMembers([]);
      await fetchData();
    } catch (err) {
      toast.error('Failed to update permissions: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  const closeCreateModal = () => {
    setShowCreateModal(false);
    setFormData({ name: '', description: '' });
    setGroupPermissions([]);
    setSelectedMembers([]);
  };

  const closeEditModal = () => {
    setShowEditModal(false);
    setEditGroupData({ id: '', name: '', description: '' });
    setSelectedMembers([]);
  };

  const updateGroup = async () => {
    if (!editGroupData.name.trim()) {
      toast.error('Group name is required');
      return;
    }

    setSaving(true);
    try {
      await api.updateGroup(editGroupData.id, {
        name: editGroupData.name,
        description: editGroupData.description
      });
      await api.updateGroupMembers(editGroupData.id, selectedMembers);
      toast.success('Group updated successfully');
      closeEditModal();
      await fetchData();
    } catch (err) {
      toast.error('Failed to update group: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  const togglePermission = (permName) => {
    setGroupPermissions(prev => 
      prev.includes(permName) 
        ? prev.filter(p => p !== permName)
        : [...prev, permName]
    );
  };

  const addPerms = (perms) => {
    const permNames = new Set(perms.map(p => p.name));
    setGroupPermissions(prev => Array.from(new Set([...prev, ...permNames])));
  };

  const removePerms = (perms) => {
    const permNames = new Set(perms.map(p => p.name));
    setGroupPermissions(prev => prev.filter(p => !permNames.has(p)));
  };

  const toggleMember = (userId) => {
    setSelectedMembers(prev => {
      const next = new Set(prev);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return Array.from(next);
    });
  };

  const getPermLabel = (perm) => perm.display_name || perm.name || perm.id || 'Permission';
  const getPermDescription = (perm) => perm.description || perm.name || '';

  const getCategoryDescription = (category) => {
    const descriptions = {
      agents: 'Control access to OTEL agents and system metrics monitoring',
      alerts: 'Manage alert rules, active alerts, and notification channels',
      channels: 'Configure notification channels for alert delivery',
      dashboards: 'Access and manage Grafana dashboards',
      groups: 'Control user group creation, modification, and membership',
      logs: 'Query and view application logs from Loki',
      tenants: 'Manage multi-tenant settings and configurations',
      traces: 'Query and view distributed traces from Tempo',
      users: 'Control user account creation, modification, and access'
    }
    return descriptions[category] || `Manage ${category} permissions and access`
  }

  const groupPermissionsByResource = () => {
    const grouped = {};
    permissions.forEach(p => {
      const resourceType = p.resource_type || 'general';
      if (!grouped[resourceType]) {
        grouped[resourceType] = [];
      }
      grouped[resourceType].push(p);
    });
    return grouped;
  };

  const filteredGroups = groups.filter(g => 
    !searchQuery || 
    g.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    g.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const sortedUsers = (users || []).slice().sort((a, b) => {
    const nameA = (a.full_name || a.username || '').toLowerCase();
    const nameB = (b.full_name || b.username || '').toLowerCase();
    return nameA.localeCompare(nameB);
  });

  if (!canManageGroups) {
    return (
      <div className="p-6">
        <Alert variant="error">
          <div className="font-semibold">Access Denied</div>
          <div className="text-sm mt-1">You don't have permission to manage groups.</div>
        </Alert>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-sre-text">Groups Management</h1>
          <p className="text-sre-text-muted mt-2">Manage groups and assign permissions that members will inherit</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Only show the header Create button when there are existing groups or when a search is active.
              When there are no groups and no search query, the centered Empty State CTA will be shown instead. */}
          {!(groups.length === 0 && !searchQuery) && (
            <Button onClick={() => setShowCreateModal(true)} size="sm">
              <span className="material-icons mr-2">add</span>
              Create Group
            </Button>
          )}
          <Button size="sm" variant="secondary" onClick={() => navigate('/users')}>
            <span className="material-icons mr-2">people</span>
            Users
          </Button>
        </div>
      </div>

      {/* Search Bar */}
      <Card>
        <div className="flex items-center gap-2">
          <Input
            placeholder="Search groups by name or description..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex-1"
          />
          <HelpTooltip text="Search groups by their name or description. The search is case-insensitive and matches partial strings." />
        </div>
      </Card>

      {/* Groups Grid */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-sre-primary"></div>
        </div>
      ) : (
        <div className="grid gap-6 grid-cols-2">
          {filteredGroups.map(group => (
            <Card key={group.id} className="p-0 relative overflow-visible bg-gradient-to-br from-sre-surface to-sre-surface/80 border-2 border-sre-border/50 hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm rounded-lg group">
              <div className="p-6">
                <div className="flex items-start gap-4 mb-4">
                  <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-sre-primary/20 to-sre-primary/10 text-sre-primary flex items-center justify-center font-semibold border border-sre-border/50 flex-shrink-0">
                    <span className="material-icons text-xl">groups</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-xl font-bold text-sre-text truncate mb-1" title={group.name}>{group.name}</h3>
                    <p className="text-sm text-sre-text-muted line-clamp-2" title={group.description || 'No description'}>
                      {group.description || 'No description provided'}
                    </p>
                  </div>
                </div>

                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <Badge variant="info" className="whitespace-nowrap text-xs px-3 py-1 font-medium">
                      <span className="material-icons text-xs mr-1">security</span>
                      {(() => { const n = (group.permissions || []).length || 0; return `${n} permission${n === 1 ? '' : 's'}` })()}
                    </Badge>
                    <Badge variant="success" className="whitespace-nowrap text-xs px-3 py-1 font-medium">
                      <span className="material-icons text-xs mr-1">person</span>
                      {group.user_count || 0} member{(group.user_count || 0) !== 1 ? 's' : ''}
                    </Badge>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2 items-center pt-2 border-t border-sre-border/30">
                  <Button size="sm" variant="ghost" className="flex items-center gap-2 hover:bg-sre-primary/10 hover:text-sre-primary transition-colors" onClick={() => openPermissionsModal(group)} aria-label={`Permissions for ${group.name}`}>
                    <span className="material-icons text-sm">security</span>
                    <span>Permissions</span>
                  </Button>

                  <Button size="sm" variant="ghost" className="flex items-center gap-2 hover:bg-sre-primary/10 hover:text-sre-primary transition-colors" onClick={() => openEditModal(group)} aria-label={`Edit ${group.name}`}>
                    <span className="material-icons text-sm">edit</span>
                    <span>Edit</span>
                  </Button>

                  <Button size="sm" variant="ghost" className="flex items-center gap-2 hover:bg-red-500/10 hover:text-red-500 transition-colors" onClick={() => setDeleteConfirm(group)} aria-label={`Delete ${group.name}`}>
                    <span className="material-icons text-sm">delete</span>
                    <span>Delete</span>
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {filteredGroups.length === 0 && !loading && (
        <Card className="text-center py-12">
          <svg className="w-16 h-16 mx-auto text-sre-text-muted mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
          </svg>
          <h3 className="text-lg font-semibold text-sre-text mb-2">
            {searchQuery ? 'No groups found' : 'No groups yet'}
          </h3>
          <p className="text-sre-text-muted mb-4">
            {searchQuery ? 'Try a different search term' : 'Create your first group to organize users and permissions'}
          </p>
          {!searchQuery && <Button onClick={() => setShowCreateModal(true)}>Create Group</Button>}
        </Card>
      )}

      {/* Create Group Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={closeCreateModal}
        closeOnOverlayClick={false}
        title="Create New Group"
        size="lg"
        footer={
          <div className="flex gap-3 justify-end">
            <Button variant="ghost" onClick={closeCreateModal} disabled={saving}>
              Cancel
            </Button>
            <Button 
              onClick={createGroup} 
              disabled={!formData.name.trim() || saving}
            >
              {saving ? 'Creating...' : 'Create Group'}
            </Button>
          </div>
        }
      >
        <div className="space-y-6">
          <div className="space-y-4 pb-4 border-b border-sre-border">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-sre-text">Group Details</h3>
              <HelpTooltip text="Basic information about the group including name and purpose." />
            </div>
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <Input
                  label="Group Name *"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g., SRE Team, DevOps, Security"
                  required
                  autoFocus
                />
              </div>
              <HelpTooltip text="A unique name for the group. This will be displayed throughout the system." />
            </div>
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <Textarea
                  label="Description"
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Describe the group's purpose and responsibilities"
                  rows={2}
                />
              </div>
              <HelpTooltip text="An optional description to explain the group's role and responsibilities." />
            </div>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-sre-text">Permissions (Optional)</h3>
                <HelpTooltip text="Configure which permissions members of this group will inherit. Permissions are organized by resource type." />
              </div>
              <div className="flex gap-3 text-xs">
                <button
                  type="button"
                  onClick={() => setGroupPermissions(permissions.map(p => p.name))}
                  className="px-2 py-1 text-sre-primary hover:bg-sre-primary/10 rounded"
                >
                  Select All
                </button>
                <button
                  type="button"
                  onClick={() => setGroupPermissions([])}
                  className="px-2 py-1 text-sre-text-muted hover:bg-sre-surface rounded"
                >
                  Clear All
                </button>
              </div>
            </div>
            
            <Alert variant="info">
              <div className="text-xs">
                Members of this group will inherit these permissions. You can add permissions now or later.
              </div>
            </Alert>

            <div className="max-h-96 overflow-y-auto space-y-3 pr-2">
              {permissions.length === 0 && (
                <div className="text-sm text-sre-text-muted">No permissions available.</div>
              )}
              {Object.entries(groupPermissionsByResource()).map(([resource, perms]) => (
                <div key={resource} className="border border-sre-border rounded-lg p-3 bg-sre-surface/20">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <h4 className="font-semibold capitalize text-sm text-sre-text">{resource}</h4>
                      <HelpTooltip text={getCategoryDescription(resource)} />
                    </div>
                    <div className="flex gap-2 text-xs">
                      <button
                        type="button"
                        onClick={() => addPerms(perms)}
                        className="px-2 py-0.5 text-sre-primary hover:bg-sre-primary/10 rounded"
                      >
                        Select
                      </button>
                      <button
                        type="button"
                        onClick={() => removePerms(perms)}
                        className="px-2 py-0.5 text-sre-text-muted hover:bg-sre-surface rounded"
                      >
                        Clear
                      </button>
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    {perms.map(perm => (
                      <label key={perm.id} className="flex items-start gap-2 p-2 hover:bg-sre-surface/50 rounded cursor-pointer">
                        <Checkbox
                          checked={groupPermissions.includes(perm.name)}
                          onChange={() => togglePermission(perm.name)}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <div className="font-medium text-sm text-sre-text break-words">{getPermLabel(perm)}</div>
                            <HelpTooltip text={getPermDescription(perm)} />
                          </div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-4">
            <h3 className="font-semibold text-sre-text">Group Members (Optional)</h3>
            <MemberList users={sortedUsers} selectedMembers={selectedMembers} toggleMember={toggleMember} />
          </div>
        </div>
      </Modal>

      {/* Edit Group Modal */}
      <Modal
        isOpen={showEditModal}
        onClose={closeEditModal}
        closeOnOverlayClick={false}
        title="Edit Group"
        size="xl"
        footer={
          <div className="flex gap-3 justify-end">
            <Button variant="ghost" onClick={closeEditModal} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={updateGroup} disabled={!editGroupData.name.trim() || saving}>
              {saving ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        }
      >
        <div className="space-y-6">
          <div className="text-sm text-sre-text-muted">
            Update group name and description. Permissions can be edited in the Permissions dialog.
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <Input
                  label="Group Name *"
                  value={editGroupData.name}
                  onChange={(e) => setEditGroupData({ ...editGroupData, name: e.target.value })}
                  placeholder="e.g., SRE Team, DevOps, Security"
                  required
                />
              </div>
              <HelpTooltip text="A unique name for the group. This will be displayed throughout the system." />
            </div>
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <Textarea
                  label="Description"
                  value={editGroupData.description}
                  onChange={(e) => setEditGroupData({ ...editGroupData, description: e.target.value })}
                  placeholder="Describe the group's purpose and responsibilities"
                  rows={3}
                />
              </div>
              <HelpTooltip text="An optional description to explain the group's role and responsibilities." />
            </div>
          </div>
          <div className="space-y-3">
            <h3 className="font-semibold text-sre-text">Group Members</h3>
            <MemberList users={sortedUsers} selectedMembers={selectedMembers} toggleMember={toggleMember} />
          </div>
        </div>
      </Modal>

      {/* Permissions Modal */}
      <Modal
        isOpen={showPermissionsModal}
        onClose={() => {
          setShowPermissionsModal(false);
          setSelectedGroup(null);
          setSelectedMembers([]);
        }}
        closeOnOverlayClick={false}
        title={`Permissions: ${selectedGroup?.name}`}
        size="lg"
        footer={
          <div className="flex gap-3 justify-end">
            <Button 
              variant="ghost" 
              onClick={() => {
                setShowPermissionsModal(false);
                setSelectedGroup(null);
                setSelectedMembers([]);
              }}
              disabled={saving}
            >
              Cancel
            </Button>
            <Button onClick={savePermissions} disabled={saving}>
              {saving ? 'Saving...' : 'Save Permissions'}
            </Button>
          </div>
        }
      >
        <div className="space-y-6">
          <Alert variant="info">
            <div className="text-sm">
              All members of this group will inherit these permissions. User-specific permissions override group permissions.
            </div>
          </Alert>

          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-sre-text">Group Members</h3>
              <HelpTooltip text="Users who are members of this group and will inherit the selected permissions." />
            </div>
            <MemberList users={sortedUsers} selectedMembers={selectedMembers} toggleMember={toggleMember} />
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="text-sm text-sre-text-muted">
                {groupPermissions.length} permission{groupPermissions.length === 1 ? '' : 's'} selected
              </div>
              <HelpTooltip text="Total number of permissions currently assigned to this group." />
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setGroupPermissions(permissions.map(p => p.name))}
                className="text-sm text-sre-primary hover:text-sre-primary-light"
              >
                Select All
              </button>
              <button
                type="button"
                onClick={() => setGroupPermissions([])}
                className="text-sm text-sre-text-muted hover:text-sre-text"
              >
                Clear All
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2 mb-4">
            <h3 className="font-semibold text-sre-text">Permissions</h3>
            <HelpTooltip text="Configure which permissions members of this group will inherit. Permissions are organized by resource type." />
          </div>

          <div className="max-h-96 overflow-y-auto space-y-4">
            {Object.entries(groupPermissionsByResource()).map(([resource, perms]) => (
              <div key={resource} className="border border-sre-border rounded-lg p-3 bg-sre-surface/30">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold capitalize text-base text-sre-text">{resource}</h3>
                    <HelpTooltip text={getCategoryDescription(resource)} />
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => addPerms(perms)}
                      className="text-xs px-2 py-1 text-sre-primary hover:bg-sre-primary/10 rounded"
                    >
                      Select All
                    </button>
                    <button
                      type="button"
                      onClick={() => removePerms(perms)}
                      className="text-xs px-2 py-1 text-sre-text-muted hover:bg-sre-surface rounded"
                    >
                      Clear
                    </button>
                  </div>
                </div>
                <div className="space-y-1.5">
                  {perms.map(perm => (
                    <label key={perm.id} className="flex items-start gap-2 p-2 hover:bg-sre-surface/50 rounded cursor-pointer">
                      <Checkbox
                        checked={groupPermissions.includes(perm.name)}
                        onChange={() => togglePermission(perm.name)}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <div className="font-medium text-sm text-sre-text break-words">{getPermLabel(perm)}</div>
                          <HelpTooltip text={getPermDescription(perm)} />
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={() => {
          deleteGroup(deleteConfirm.id);
          setDeleteConfirm(null);
        }}
        title="Delete Group"
        message={`Are you sure you want to delete "${deleteConfirm?.name}"? This action cannot be undone.`}
        confirmText="Delete"
        variant="danger"
      />
    </div>
  );
}
