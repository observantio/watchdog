import { useEffect, useState, useCallback } from 'react'
import { Card, Button, Input, Badge, Spinner, Modal, Checkbox } from '../components/ui'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../contexts/ToastContext'
import PermissionEditor from '../components/PermissionEditor'
import ConfirmModal from '../components/ConfirmModal'
import * as api from '../api'

export default function UsersPage() {
  const toast = useToast();
  const [users, setUsers] = useState([])
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [showUserForm, setShowUserForm] = useState(false)
  const [editingUser, setEditingUser] = useState(null)
  const [showEditModal, setShowEditModal] = useState(false)
  const [editUserData, setEditUserData] = useState({
    id: '',
    username: '',
    email: '',
    full_name: '',
    role: 'user',
    is_active: true
  })
  const [searchQuery, setSearchQuery] = useState('')
  const [confirmDialog, setConfirmDialog] = useState({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: null
  })
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    full_name: '',
    role: 'user'
  })
  const { user: currentUser, hasPermission } = useAuth()

  const canManageUsers = hasPermission('manage:users')

  const generatePassword = () => {
    const length = 16;
    const charset = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*';
    let password = '';
    for (let i = 0; i < length; i++) {
      password += charset.charAt(Math.floor(Math.random() * charset.length));
    }
    return password;
  };

  const handleGeneratePassword = () => {
    const newPassword = generatePassword();
    setFormData({ ...formData, password: newPassword });
    toast.success('Password generated successfully');
  };

  const handleCopyPassword = async () => {
    try {
      await navigator.clipboard.writeText(formData.password);
      toast.success('Password copied to clipboard');
    } catch (err) {
      toast.error('Failed to copy password: ' + (err?.message || 'Unknown error'));
      console.error('Failed to copy password:', err);
    }
  };

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      if (canManageUsers) {
        const usersData = await api.getUsers()
        setUsers(usersData)
        const groupsData = await api.getGroups()
        setGroups(groupsData)
      }
    } catch (error) {
      setUsers([])
      setGroups([])
      toast.error('Error loading data: ' + (error?.message || 'Unknown error'));
      console.error('Error loading data:', error)
    } finally {
      setLoading(false)
    }
  }, [canManageUsers, currentUser, toast])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleCreateUser = async (e) => {
    e.preventDefault()
    try {
      await api.createUser(formData)
      setShowUserForm(false)
      setFormData({ username: '', email: '', password: '', full_name: '', role: 'user' })
      toast.success('User created successfully');
      loadData()
    } catch (error) {
      const msg = error?.body?.detail || error?.body?.message || (() => {
        try {
          const parsed = JSON.parse(error?.message || '')
          return parsed.detail || parsed.message || error.message
        } catch (e) {
          console.error('Failed to parse error message', e)
          return error?.message || 'Unknown error'
        }
      })()
      toast.error('Error creating user: ' + msg);
    }
  }

  const handleDeleteUser = async (userId) => {
    setConfirmDialog({
      isOpen: true,
      title: 'Delete User',
      message: 'Are you sure you want to delete this user? This action cannot be undone.',
      onConfirm: async () => {
        try {
          await api.deleteUser(userId)
          setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null })
          toast.success('User deleted successfully');
          loadData()
        } catch (error) {
          toast.error('Error deleting user: ' + error.message);
        }
      }
    })
  }

  const handleEditPermissions = (user) => {
    setEditingUser(user)
  }

  const openEditUser = (user) => {
    setEditUserData({
      id: user.id,
      username: user.username || '',
      email: user.email || '',
      full_name: user.full_name || '',
      role: user.role || 'user',
      is_active: user.is_active ?? true
    })
    setShowEditModal(true)
  }

  const closeEditUser = () => {
    setShowEditModal(false)
    setEditUserData({ id: '', username: '', email: '', full_name: '', role: 'user', is_active: true })
  }

  const handleUpdateUser = async () => {
    try {
      await api.updateUser(editUserData.id, {
        email: editUserData.email,
        full_name: editUserData.full_name,
        role: editUserData.role,
        is_active: editUserData.is_active
      })
      toast.success('User updated successfully')
      closeEditUser()
      loadData()
    } catch (error) {
      toast.error('Error updating user: ' + error.message)
    }
  }

  const handleSavePermissions = async (updates) => {
    try {
      await api.updateUser(editingUser.id, updates)
    } catch (error) {
      toast.error('Error updating permissions: ' + (error?.message || 'Unknown error'));
      console.error('Error updating permissions:', error);
      throw error
    }
  }

  const filteredUsers = users.filter(u => 
    !searchQuery || 
    u.username?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    u.email?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    u.full_name?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  if (!canManageUsers) {
    return (
      <div className="text-center py-12">
        <p className="text-sre-text-muted">You do not have permission to manage users.</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-sre-text mb-2">
          User Management
        </h1>
        <p className="text-sre-text-muted">
          Manage users, roles, and permissions
        </p>
      </div>

      {/* Search Bar */}
      <Card className="mb-6">
        <Input
          placeholder="Search users by username, email, or name..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full"
        />
      </Card>

      <Card
        title="Users"
        subtitle={`Returned ${filteredUsers.length} user${filteredUsers.length === 1 ? '' : 's'}${searchQuery ? ' (filtered)' : ''} from the database.`}
        action={
          <Button onClick={() => setShowUserForm(!showUserForm)} size="sm">
            {showUserForm ? 'Cancel' : 'Add User'}
          </Button>
        }
      >
            {showUserForm && (
              <form onSubmit={handleCreateUser} className="mb-6 p-4 bg-sre-bg-alt rounded border border-sre-border space-y-3">
                <Input
                  placeholder="Username"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  required
                />
                <Input
                  placeholder="Email"
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  required
                />
                <div className="space-y-2">
                  <Input
                    placeholder="Password (min 8 characters)"
                    type="password"
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    required
                  />
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={handleGeneratePassword}
                      className="flex-1"
                    >
                      <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      Generate
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={handleCopyPassword}
                      disabled={!formData.password}
                      className="flex-1"
                    >
                      <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                      Copy
                    </Button>
                  </div>
                </div>
                <Input
                  placeholder="Full Name (optional)"
                  value={formData.full_name}
                  onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                />
                <select
                  value={formData.role}
                  onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                  className="w-full px-3 pr-10 py-2 bg-sre-bg border border-sre-border rounded text-sre-text"
                >
                  <option value="viewer">Viewer</option>
                  <option value="user">User</option>
                  <option value="admin">Admin</option>
                </select>
                <Button type="submit" variant="primary" className="w-full">
                  Create User
                </Button>
              </form>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {filteredUsers.length === 0 ? (
                <div className="text-center py-8 text-sre-text-muted">
                  {searchQuery ? 'No users found matching your search' : 'No users yet'}
                </div>
              ) : (
                filteredUsers.map((u) => {
                let roleVariant = 'default';
                if (u.role === 'admin') {
                  roleVariant = 'error';
                } else if (u.role === 'user') {
                  roleVariant = 'info';
                }
                return (
                <div key={u.id} className="p-4 bg-sre-surface/50 rounded-sm border border-sre-border  transition-all flex gap-4">
                  <div className="w-12 h-12 flex-none  bg-sre-primary/10 text-sre-primary flex items-center justify-center font-semibold text-sm">
                    {u.username ? u.username.charAt(0).toUpperCase() : 'U'}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-4">
                      <div className="truncate">
                        <div className="font-semibold text-sre-text truncate">{u.username}</div>
                        <div className="text-xs text-sre-text-muted truncate">{u.email}</div>
                      </div>
                      <div className="hidden sm:flex items-center gap-2">
                        <Badge variant={roleVariant}>{u.role}</Badge>
                        {!u.is_active && <Badge variant="warning">Inactive</Badge>}
                        {u.group_ids?.length > 0 && (
                          <Badge variant="success">{u.group_ids.length} group{u.group_ids.length > 1 ? 's' : ''}</Badge>
                        )}
                      </div>
                    </div>

                    <div className="mt-3 flex items-center justify-between">
                      <div className="flex items-center gap-2 sm:hidden">
                        <Badge variant={roleVariant}>{u.role}</Badge>
                        {!u.is_active && <Badge variant="warning">Inactive</Badge>}
                      </div>

                      <div className="flex gap-2">
                        <Button variant="ghost" size="sm" onClick={() => openEditUser(u)} >
                          Edit
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => handleEditPermissions(u)} className=" text-blue-500">
                          Permissions
                        </Button>
                        {u.id !== currentUser?.id && (
                          <Button variant="ghost" size="sm" onClick={() => handleDeleteUser(u.id)} className="text-red-500">
                            Delete
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )
              })
              )}

            {/* Edit User Modal */}
            <Modal
              isOpen={showEditModal}
              onClose={closeEditUser}
              title="Edit User"
              size="xl"
              footer={
                <div className="flex gap-3 justify-end">
                  <Button variant="ghost" onClick={closeEditUser}>
                    Cancel
                  </Button>
                  <Button onClick={handleUpdateUser}>
                    Save Changes
                  </Button>
                </div>
              }
            >
              <div className="space-y-6">
                <div className="text-sm text-sre-text-muted">
                  Update user profile details. Permissions are managed separately in the Permissions editor.
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <Input
                    label="Username"
                    value={editUserData.username}
                    disabled
                  />
                  <Input
                    label="Email"
                    type="email"
                    value={editUserData.email}
                    onChange={(e) => setEditUserData({ ...editUserData, email: e.target.value })}
                    required
                  />
                  <Input
                    label="Full Name"
                    value={editUserData.full_name}
                    onChange={(e) => setEditUserData({ ...editUserData, full_name: e.target.value })}
                  />
                  <div>
                    <label htmlFor="role" className="block text-sm font-medium text-sre-text mb-2">Role</label>
                    <select
                      value={editUserData.role}
                      onChange={(e) => setEditUserData({ ...editUserData, role: e.target.value })}
                      className="w-full px-3 pr-10 py-2 bg-sre-bg border border-sre-border rounded text-sre-text"
                    >
                      <option value="viewer">Viewer</option>
                      <option value="user">User</option>
                      <option value="admin">Admin</option>
                    </select>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox
                    checked={editUserData.is_active}
                    onChange={() => setEditUserData({ ...editUserData, is_active: !editUserData.is_active })}
                    label="Active"
                  />
                </div>
              </div>
            </Modal>
            </div>
          </Card>

      {editingUser && (
        <PermissionEditor
          user={editingUser}
          groups={groups}
          onClose={() => {
            setEditingUser(null)
            loadData()
          }}
          onSave={handleSavePermissions}
        />
      )}

      <ConfirmModal
        isOpen={confirmDialog.isOpen}
        title={confirmDialog.title}
        message={confirmDialog.message}
        onConfirm={confirmDialog.onConfirm}
        onCancel={() => setConfirmDialog({ isOpen: false, title: '', message: '', onConfirm: null })}
        confirmText="Delete"
        variant="danger"
      />
    </div>
  )
}
