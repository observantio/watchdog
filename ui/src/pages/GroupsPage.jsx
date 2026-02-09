/**
 * Groups Management Page
 * Manage groups and assign permissions with least privilege enforcement
*/

import { useState, useEffect } from 'react';
import { Card, Button, Input, Textarea, Modal, ConfirmDialog, Badge, Alert, Checkbox } from '../components/ui';
import { usePermissions } from '../hooks/usePermissions';
import { useToast } from '../contexts/ToastContext';
import * as api from '../api';

export default function GroupsPage() {
  const { canManageGroups } = usePermissions();
  const toast = useToast();
  const [groups, setGroups] = useState([]);
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
    } catch (err) {
      toast.error('Failed to load groups: ' + err.message);
      console.error('Error loading data:', err);
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
      
      toast.success('Group created successfully');
      setShowCreateModal(false);
      setFormData({ name: '', description: '' });
      setGroupPermissions([]);
      await fetchData();
    } catch (err) {
      toast.error('Failed to create group: ' + err.message);
      console.error('Create group error:', err);
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
      console.error('Delete group error:', err);
    }
  };

  const openPermissionsModal = (group) => {
    setSelectedGroup(group);
    // Set current group permissions
    const currentPerms = group.permissions?.map(p => p.name || p) || [];
    setGroupPermissions(currentPerms);
    setShowPermissionsModal(true);
  };

  const openEditModal = (group) => {
    setEditGroupData({
      id: group.id,
      name: group.name || '',
      description: group.description || ''
    });
    setShowEditModal(true);
  };

  const savePermissions = async () => {
    setSaving(true);
    try {
      await api.updateGroupPermissions(selectedGroup.id, groupPermissions);
      toast.success('Permissions updated successfully');
      setShowPermissionsModal(false);
      setSelectedGroup(null);
      await fetchData();
    } catch (err) {
      toast.error('Failed to update permissions: ' + err.message);
      console.error('Save permissions error:', err);
    } finally {
      setSaving(false);
    }
  };

  const closeCreateModal = () => {
    setShowCreateModal(false);
    setFormData({ name: '', description: '' });
    setGroupPermissions([]);
  };

  const closeEditModal = () => {
    setShowEditModal(false);
    setEditGroupData({ id: '', name: '', description: '' });
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
      toast.success('Group updated successfully');
      closeEditModal();
      await fetchData();
    } catch (err) {
      toast.error('Failed to update group: ' + err.message);
      console.error('Update group error:', err);
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

  const getPermLabel = (perm) => perm.display_name || perm.name || perm.id || 'Permission';
  const getPermDescription = (perm) => perm.description || perm.name || '';

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
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-sre-text">Groups Management</h1>
          <p className="text-sre-text-muted mt-2">Manage groups and assign permissions that members will inherit</p>
        </div>
        <Button onClick={() => setShowCreateModal(true)}>
          <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Create Group
        </Button>
      </div>

      {/* Search Bar */}
      <Card>
        <Input
          placeholder="Search groups by name or description..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full"
        />
      </Card>

      {/* Groups Grid */}
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-sre-primary"></div>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredGroups.map(group => (
            <Card key={group.id} className="hover:border-sre-primary/50 transition-all">
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1">
                  <h3 className="text-lg font-semibold text-sre-text">{group.name}</h3>
                  <p className="text-sm text-sre-text-muted mt-1">
                    {group.description || 'No description'}
                  </p>
                </div>
                <Badge variant="info">
                  {group.permissions?.length || 0} perms
                </Badge>
              </div>

              <div className="flex gap-2 mt-4">
                <Button
                  size="sm"
                  variant="secondary"
                  className="flex-1"
                  onClick={() => openPermissionsModal(group)}
                >
                  <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                  Permissions
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => openEditModal(group)}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5h2m2 0h3a2 2 0 012 2v3m0 4v3a2 2 0 01-2 2h-3m-4 0H7a2 2 0 01-2-2v-3m0-4V7a2 2 0 012-2h3" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.5 5.5l-9 9-3 1 1-3 9-9" />
                  </svg>
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  onClick={() => setDeleteConfirm(group)}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </Button>
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
            <h3 className="font-semibold text-sre-text">Group Details</h3>
            <Input
              label="Group Name *"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="e.g., SRE Team, DevOps, Security"
              required
              autoFocus
            />
            <Textarea
              label="Description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Describe the group's purpose and responsibilities"
              rows={2}
            />
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-sre-text">Permissions (Optional)</h3>
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
                    <h4 className="font-semibold capitalize text-sm text-sre-text">{resource}</h4>
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
                      <label key={perm.id} className="flex justify-between gap-5 p-2 hover:bg-sre-surface/50 rounded cursor-pointer group">
                        <Checkbox
                          checked={groupPermissions.includes(perm.name)}
                          onChange={() => togglePermission(perm.name)}
                        />
                        <div className="flex-1">
                          <div className="text-xs font-medium text-sre-text break-words">{getPermLabel(perm)}</div>
                          <div className="text-xs text-sre-text-muted break-words">{getPermDescription(perm)}</div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Modal>

      {/* Edit Group Modal */}
      <Modal
        isOpen={showEditModal}
        onClose={closeEditModal}
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
            <Input
              label="Group Name *"
              value={editGroupData.name}
              onChange={(e) => setEditGroupData({ ...editGroupData, name: e.target.value })}
              placeholder="e.g., SRE Team, DevOps, Security"
              required
            />
            <Textarea
              label="Description"
              value={editGroupData.description}
              onChange={(e) => setEditGroupData({ ...editGroupData, description: e.target.value })}
              placeholder="Describe the group's purpose and responsibilities"
              rows={3}
            />
          </div>
        </div>
      </Modal>

      {/* Permissions Modal */}
      <Modal
        isOpen={showPermissionsModal}
        onClose={() => {
          setShowPermissionsModal(false);
          setSelectedGroup(null);
        }}
        title={`Permissions: ${selectedGroup?.name}`}
        size="lg"
        footer={
          <div className="flex gap-3 justify-end">
            <Button 
              variant="ghost" 
              onClick={() => {
                setShowPermissionsModal(false);
                setSelectedGroup(null);
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

          <div className="flex items-center justify-between">
            <div className="text-sm text-sre-text-muted">
                {groupPermissions.length} permission{groupPermissions.length === 1 ? '' : 's'} selected
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

          <div className="max-h-96 overflow-y-auto space-y-4">
            {Object.entries(groupPermissionsByResource()).map(([resource, perms]) => (
              <div key={resource} className="border border-sre-border rounded-lg p-4 bg-sre-surface/30">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold capitalize text-lg text-sre-text">{resource}</h3>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => addPerms(perms)}
                      className="text-sm text-sre-primary hover:text-sre-primary-light"
                    >
                      Select All
                    </button>
                    <button
                      type="button"
                      onClick={() => removePerms(perms)}
                      className="text-sm text-sre-text-muted hover:text-sre-text"
                    >
                      Clear
                    </button>
                  </div>
                </div>
                <div className="space-y-2">
                  {perms.map(perm => (
                    <label key={perm.id} className="flex items-start gap-3 p-3 hover:bg-sre-surface/50 rounded cursor-pointer">
                      <Checkbox
                        checked={groupPermissions.includes(perm.name)}
                        onChange={() => togglePermission(perm.name)}
                      />
                      <div className="flex-1">
                        <div className="font-medium text-sre-text break-words">{getPermLabel(perm)}</div>
                        <div className="text-sm text-sre-text-muted break-words">{getPermDescription(perm)}</div>
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
