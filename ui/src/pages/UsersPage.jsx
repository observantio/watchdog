import { useEffect, useState, useCallback } from "react";
import {
  Card,
  Button,
  Input,
  Badge,
  Spinner,
  Modal,
  Checkbox,
} from "../components/ui";
import CreateUserModal from "../components/users/CreateUserModal";
import { useAuth } from "../contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import { useToast } from "../contexts/ToastContext";
import PermissionEditor from "../components/PermissionEditor";
import ConfirmModal from "../components/ConfirmModal";
import HelpTooltip from "../components/HelpTooltip";
import TwoFactorModal from "../components/TwoFactorModal";
import * as api from "../api";
import { USER_ROLES } from "../utils/constants";
import {
  getRoleVariant,
  getUserInitials,
} from "../components/users/userUiUtils";
import { copyToClipboard as clipboardCopy } from "../utils/helpers";

export default function UsersPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editUserData, setEditUserData] = useState({
    id: "",
    username: "",
    email: "",
    full_name: "",
    role: "user",
    is_active: true,
    must_setup_mfa: false,
  });
  const [searchQuery, setSearchQuery] = useState("");
  const [confirmDialog, setConfirmDialog] = useState({
    isOpen: false,
    title: "",
    message: "",
    onConfirm: null,
  });
  const [resetTargetUser, setResetTargetUser] = useState(null);
  const [resetInProgress, setResetInProgress] = useState(false);
  const [tempPasswordResult, setTempPasswordResult] = useState(null);
  const [selectedUser, setSelectedUser] = useState(null);
  const [showTwoFactor, setShowTwoFactor] = useState(false);

  const { user: currentUser, hasPermission } = useAuth();

  const isCurrentUserAdmin = currentUser?.role === "admin";
  const canManageUsers =
    isCurrentUserAdmin ||
    hasPermission("manage:users") ||
    hasPermission("manage:tenants");
  const canDeleteUsers = isCurrentUserAdmin;
  const canResetPasswords =
    isCurrentUserAdmin ||
    hasPermission("manage:users") ||
    hasPermission("manage:tenants");
  const canEditAllUserFields =
    isCurrentUserAdmin || hasPermission("manage:users");
  const canCreateUsers =
    isCurrentUserAdmin ||
    hasPermission("manage:users") ||
    hasPermission("create:users");
  const canEditUserPermissions =
    isCurrentUserAdmin ||
    hasPermission("manage:users") ||
    hasPermission("update:user_permissions");

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      if (canManageUsers) {
        const usersData = await api.getUsers();
        setUsers(usersData);
        try {
          const groupsData = await api.getGroups();
          setGroups(groupsData);
        } catch {
          setGroups([]);
        }
      }
    } catch (error) {
      setUsers([]);
      setGroups([]);
      toast.error("Error loading data: " + (error?.message || "Unknown error"));
    } finally {
      setLoading(false);
    }
  }, [canManageUsers, toast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleDeleteUser = async (userId) => {
    setConfirmDialog({
      isOpen: true,
      title: "Delete User",
      message:
        "Are you sure you want to delete this user? This action cannot be undone.",
      onConfirm: async () => {
        try {
          await api.deleteUser(userId);
          setConfirmDialog({
            isOpen: false,
            title: "",
            message: "",
            onConfirm: null,
          });
          toast.success("User deleted successfully");
          loadData();
        } catch (error) {
          toast.error("Error deleting user: " + error.message);
        }
      },
    });
  };

  const handleEditPermissions = (user) => {
    setEditingUser(user);
  };

  const handleResetPasswordTemp = async (user) => {
    setResetTargetUser(user);
  };

  const confirmResetPasswordTemp = async () => {
    if (!resetTargetUser) return;
    setResetInProgress(true);
    try {
      const res = await api.resetUserPasswordTemp(resetTargetUser.id);
      setTempPasswordResult({
        userId: resetTargetUser.id,
        username: resetTargetUser.username,
        temporary_password: res?.temporary_password || "",
        email_sent: !!res?.email_sent,
        message: res?.message || "Temporary password generated.",
      });
      toast.success("Temporary password generated");
      setResetTargetUser(null);
      loadData();
    } catch (error) {
      toast.error(
        "Error resetting password: " +
          (error?.body?.detail || error?.message || "Unknown error"),
      );
    } finally {
      setResetInProgress(false);
    }
  };

  const openEditUser = (user) => {
    setEditUserData({
      id: user.id,
      username: user.username || "",
      email: user.email || "",
      full_name: user.full_name || "",
      role: user.role || "user",
      is_active: user.is_active ?? true,
      must_setup_mfa: user.must_setup_mfa ?? false,
    });
    setShowEditModal(true);
  };

  const closeEditUser = () => {
    setShowEditModal(false);
    setEditUserData({
      id: "",
      username: "",
      email: "",
      full_name: "",
      role: "user",
      is_active: true,
      must_setup_mfa: false,
    });
  };

  const handleUpdateUser = async () => {
    try {
      const payload = canEditAllUserFields
        ? {
            username: editUserData.username,
            full_name: editUserData.full_name,
            role: editUserData.role,
            is_active: editUserData.is_active,
            must_setup_mfa: editUserData.must_setup_mfa,
          }
        : {
            is_active: editUserData.is_active,
          };
      await api.updateUser(editUserData.id, payload);
      toast.success("User updated successfully");
      closeEditUser();
      loadData();
    } catch (error) {
      toast.error("Error updating user: " + error.message);
    }
  };

  const handleSavePermissions = async (updates) => {
    try {
      await api.updateUser(editingUser.id, updates);
    } catch (error) {
      toast.error(
        "Error updating permissions: " + (error?.message || "Unknown error"),
      );
      throw error;
    }
  };

  const filteredUsers = users.filter(
    (u) =>
      !searchQuery ||
      u.username?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.email?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      u.full_name?.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  if (!canManageUsers) {
    return (
      <div className="text-center py-12">
        <p className="text-sre-text-muted">
          You do not have permission to manage users.
        </p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-sre-text mb-2">
            User Management
          </h1>
          <p className="text-sre-text-muted">
            Manage users, roles, and permissions
          </p>
        </div>
        {/* Show header Create button only when there are users or a search is active. When no users exist the centered empty state CTA is shown instead. */}
        {!(users.length === 0 && !searchQuery) && (
          <div className="flex items-center gap-3">
            {canCreateUsers && (
              <Button
                onClick={() => setShowCreateModal(true)}
                size="sm"
                variant="primary"
              >
                Create User
              </Button>
            )}
            <Button
              size="sm"
              variant="secondary"
              onClick={() => navigate("/groups")}
            >
              <span className="material-icons mr-2">groups</span>Groups
            </Button>
          </div>
        )}
      </div>

      {/* Search Bar */}
      <Card className="mb-6">
        <div className="flex items-center gap-2">
          <Input
            placeholder="Search users by username, email, or name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex-1"
          />
          <HelpTooltip text="Search users by their username, email address, or full name. The search is case-insensitive and matches partial strings." />
        </div>
      </Card>

      <Card
        title="Users"
        subtitle={`We've found ${filteredUsers.length} user${filteredUsers.length === 1 ? "" : "s"} from the database${searchQuery ? " (filtered)" : ""}`}
        className="border-0"
      >
        <CreateUserModal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          onCreated={loadData}
          groups={groups}
          users={users}
        />

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {filteredUsers.length === 0 ? (
            <div className="text-center py-12">
              <h3 className="text-lg font-semibold text-sre-text mb-2">
                {searchQuery ? "No users found" : "No users yet"}
              </h3>
              <p className="text-sre-text-muted mb-4">
                {searchQuery
                  ? "Try a different search term"
                  : "Create your first user to get started"}
              </p>
              {!searchQuery && canCreateUsers && (
                <div>
                  <Button onClick={() => setShowCreateModal(true)}>
                    Create User
                  </Button>
                </div>
              )}
            </div>
          ) : (
            filteredUsers.map((u) => {
              const roleVariant = getRoleVariant(u.role);
              const initials = getUserInitials(u);
              return (
                <Card
                  key={u.id}
                  className={`p-0 relative overflow-visible bg-gradient-to-br from-sre-surface to-sre-surface/80 border border-sre-border hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm rounded-lg group`}
                >
                  <div className="p-6">
                    <div className="flex items-start gap-4 mb-4">
                      <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-sre-primary/20 to-sre-primary/10 text-sre-primary flex items-center justify-center font-semibold border border-sre-border/50 flex-shrink-0">
                        {initials}
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="text-xl font-bold text-sre-text truncate mb-1">
                          {u.username}
                        </h3>
                        <p className="text-sm text-sre-text-muted line-clamp-2">
                          {u.email}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center justify-between mb-4">
                      <div className="flex flex-wrap items-center gap-3">
                        <Badge
                          variant={roleVariant}
                          className="whitespace-nowrap text-xs px-3 py-1 font-medium"
                        >
                          {u.role}
                        </Badge>
                        {!u.is_active && (
                          <Badge
                            variant="warning"
                            className="whitespace-nowrap text-xs px-3 py-1 font-medium"
                          >
                            Inactive
                          </Badge>
                        )}
                        <Badge
                          variant="success"
                          className="whitespace-nowrap text-xs px-3 py-1 font-medium"
                        >
                          {u.group_ids?.length || 0} group
                          {(u.group_ids?.length || 0) !== 1 ? "s" : ""}
                        </Badge>
                        <Badge
                          variant="info"
                          className="whitespace-nowrap text-xs px-3 py-1 font-medium"
                        >
                          {u.permissions?.length || 0} permission
                          {(u.permissions?.length || 0) !== 1 ? "s" : ""}
                        </Badge>
                        {u.must_setup_mfa && (
                          <Badge
                            variant="danger"
                            className="whitespace-nowrap text-xs px-3 py-1 font-medium"
                          >
                            MFA required
                          </Badge>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-2 items-center pt-2 border-t border-sre-border/30">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="flex items-center gap-1.5 hover:bg-sre-primary/10 hover:text-sre-primary transition-colors"
                        onClick={() => openEditUser(u)}
                        aria-label={`Edit ${u.username}`}
                      >
                        <span className="material-icons text-sm" aria-hidden>
                          edit
                        </span>
                        <span>Edit</span>
                      </Button>
                      {canEditUserPermissions && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="flex items-center gap-1.5 hover:bg-sre-primary/10 hover:text-sre-primary transition-colors"
                          onClick={() => handleEditPermissions(u)}
                          aria-label={`Edit permissions for ${u.username}`}
                        >
                          <span className="material-icons text-sm" aria-hidden>
                            manage_accounts
                          </span>
                          <span>Permissions</span>
                        </Button>
                      )}
                      {u.id !== currentUser?.id &&
                        canResetPasswords &&
                        u.role !== "admin" && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="flex items-center gap-1.5 hover:bg-yellow-500/10 hover:text-yellow-600 transition-colors"
                            onClick={() => handleResetPasswordTemp(u)}
                            aria-label={`Reset password for ${u.username}`}
                          >
                            <span
                              className="material-icons text-sm"
                              aria-hidden
                            >
                              password
                            </span>
                            <span>Reset Password</span>
                          </Button>
                        )}
                      {u.id !== currentUser?.id &&
                        canDeleteUsers &&
                        u.role !== "admin" && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="flex items-center gap-1.5 hover:bg-red-500/10 hover:text-red-500 transition-colors"
                            onClick={() => handleDeleteUser(u.id)}
                            aria-label={`Delete ${u.username}`}
                          >
                            <span
                              className="material-icons text-sm"
                              aria-hidden
                            >
                              delete
                            </span>
                            <span>Delete</span>
                          </Button>
                        )}
                    </div>
                  </div>
                </Card>
              );
            })
          )}

          {/* Edit User Modal */}
          <Modal
            isOpen={showEditModal}
            onClose={closeEditUser}
            title="Edit User"
            size="xl"
            closeOnOverlayClick={false}
            footer={
              <div className="flex gap-3 justify-end">
                <Button variant="ghost" onClick={closeEditUser}>
                  Cancel
                </Button>
                <Button onClick={handleUpdateUser}>Save Changes</Button>
              </div>
            }
          >
            <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="flex items-start gap-2">
                  <div className="flex-1">
                    <Input
                      label="Username"
                      value={editUserData.username}
                      onChange={(e) =>
                        setEditUserData({
                          ...editUserData,
                          username: e.target.value.toLowerCase(),
                        })
                      }
                      disabled={!canEditAllUserFields}
                    />
                  </div>
                  <HelpTooltip text="Unique username for this user. Must be unique system-wide." />
                </div>
                <div className="flex items-start gap-2">
                  <div className="flex-1">
                    <Input
                      label="Email"
                      type="email"
                      value={editUserData.email}
                      disabled
                      required
                    />
                  </div>
                  <HelpTooltip text="Email is managed externally and cannot be edited here." />
                </div>
                <div className="flex items-start gap-2">
                  <div className="flex-1">
                    <Input
                      label="Full Name"
                      value={editUserData.full_name}
                      onChange={(e) =>
                        setEditUserData({
                          ...editUserData,
                          full_name: e.target.value,
                        })
                      }
                      disabled={!canEditAllUserFields}
                    />
                  </div>
                  <HelpTooltip text="The display name for this user, shown throughout the interface." />
                </div>
                <div className="flex items-start gap-2">
                  <div className="flex-1">
                    <label
                      htmlFor="role"
                      className="block text-sm font-medium text-sre-text mb-2"
                    >
                      Role
                    </label>
                    <select
                      value={editUserData.role}
                      onChange={(e) =>
                        setEditUserData({
                          ...editUserData,
                          role: e.target.value,
                        })
                      }
                      className="w-full px-3 pr-10 py-2 bg-sre-bg border border-sre-border rounded text-sre-text"
                      disabled={
                        !canEditAllUserFields ||
                        (editUserData.role === "admin" && !isCurrentUserAdmin)
                      }
                    >
                      {USER_ROLES.map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <HelpTooltip text="The role determines the user's permissions. Admin has full access, User has limited access." />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  checked={editUserData.is_active}
                  onChange={() =>
                    setEditUserData({
                      ...editUserData,
                      is_active: !editUserData.is_active,
                    })
                  }
                  label="Active"
                  disabled={
                    editUserData.id === currentUser?.id ||
                    (editUserData.role === "admin" && !isCurrentUserAdmin)
                  }
                />
                <HelpTooltip
                  text={
                    editUserData.id === currentUser?.id
                      ? "You cannot disable your own account"
                      : editUserData.role === "admin" && !isCurrentUserAdmin
                        ? "Only administrators can modify admin accounts"
                        : "Inactive users cannot log in but their account data is preserved."
                  }
                />
              </div>

              <div className="flex items-center gap-2 mt-2">
                <Checkbox
                  checked={editUserData.must_setup_mfa}
                  onChange={() =>
                    setEditUserData({
                      ...editUserData,
                      must_setup_mfa: !editUserData.must_setup_mfa,
                    })
                  }
                  label="Require Two‑Factor"
                  disabled={
                    !canEditAllUserFields ||
                    editUserData.id === currentUser?.id ||
                    (editUserData.role === "admin" && !isCurrentUserAdmin)
                  }
                />
                <HelpTooltip text="Require this user to enroll in 2FA at next login." />
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
            setEditingUser(null);
            loadData();
          }}
          onSave={handleSavePermissions}
        />
      )}

      {/* User Profile Modal */}
      {selectedUser && (
        <Modal
          isOpen={!!selectedUser}
          onClose={() => setSelectedUser(null)}
          title={`${selectedUser.username}'s Profile`}
          size="md"
        >
          <div className="space-y-6">
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded-md bg-sre-primary/10 text-sre-primary flex items-center justify-center font-semibold text-lg border border-sre-border">
                {getUserInitials(selectedUser)}
              </div>
              <div>
                <h3 className="text-lg font-semibold text-sre-text">
                  {selectedUser.username}
                </h3>
                <p className="text-sm text-sre-text-muted">
                  {selectedUser.email}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-sre-text mb-1">
                  Full Name
                </label>
                <p className="text-sm text-sre-text-muted">
                  {selectedUser.full_name || "Not set"}
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-sre-text mb-1">
                  Role
                </label>
                <p className="text-sm text-sre-text-muted capitalize">
                  {selectedUser.role}
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-sre-text mb-1">
                  Status
                </label>
                <p className="text-sm text-sre-text-muted">
                  {selectedUser.is_active ? "Active" : "Inactive"}
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-sre-text mb-1">
                  Groups
                </label>
                <p className="text-sm text-sre-text-muted">
                  {(selectedUser.group_ids || []).length} group
                  {(selectedUser.group_ids || []).length !== 1 ? "s" : ""}
                </p>
              </div>
            </div>

            <div className="mt-4 flex gap-2">
              {selectedUser.id === currentUser?.id && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setShowTwoFactor(true)}
                >
                  Manage Two‑Factor
                </Button>
              )}
              {canManageUsers && selectedUser.id !== currentUser?.id && (
                <Button
                  size="sm"
                  variant="danger"
                  onClick={async () => {
                    try {
                      await api.resetUserMFA(selectedUser.id);
                      toast.success("User 2FA has been reset");
                      loadData();
                    } catch (err) {
                      toast.error(
                        "Failed to reset user 2FA: " +
                          (err?.message || "Unknown"),
                      );
                    }
                  }}
                >
                  Reset 2FA
                </Button>
              )}
            </div>
          </div>
        </Modal>
      )}

      {resetTargetUser && (
        <Modal
          isOpen={!!resetTargetUser}
          onClose={() => {
            if (!resetInProgress) setResetTargetUser(null);
          }}
          title="Reset User Password"
          size="md"
          closeOnOverlayClick={false}
          footer={
            <div className="flex gap-2 justify-end">
              <Button
                variant="ghost"
                onClick={() => setResetTargetUser(null)}
                disabled={resetInProgress}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={confirmResetPasswordTemp}
                loading={resetInProgress}
              >
                {resetInProgress
                  ? "Resetting..."
                  : "Generate Temporary Password"}
              </Button>
            </div>
          }
        >
          <p className="text-sm text-sre-text-muted">
            This will revoke active sessions immediately and require{" "}
            <strong>{resetTargetUser.username}</strong> to change their password
            at next login.
          </p>
        </Modal>
      )}

      {tempPasswordResult && (
        <Modal
          isOpen={!!tempPasswordResult}
          onClose={() => setTempPasswordResult(null)}
          title="Temporary Password Generated"
          size="md"
          closeOnOverlayClick={false}
          footer={
            <div className="flex gap-2 justify-end">
              <Button
                variant="ghost"
                onClick={() => setTempPasswordResult(null)}
              >
                Close
              </Button>
            </div>
          }
        >
          <div className="space-y-3">
            <p className="text-sm text-sre-text-muted">
              {tempPasswordResult.message}
            </p>
            <div className="p-3 rounded border border-sre-border bg-sre-bg-alt">
              <div className="text-xs text-sre-text-muted mb-1">
                Temporary password (shown once)
              </div>
              <div className="font-mono text-sm text-sre-text break-all">
                {tempPasswordResult.temporary_password}
              </div>
            </div>
            <div className="text-xs text-sre-text-muted">
              Email delivery:{" "}
              {tempPasswordResult.email_sent ? "sent" : "not sent"}
            </div>
            <div>
              <Button
                variant="secondary"
                onClick={async () => {
                  const ok = await clipboardCopy(
                    tempPasswordResult.temporary_password,
                  );
                  if (ok) toast.success("Temporary password copied");
                  else toast.error("Unable to copy temporary password");
                }}
              >
                Copy Temporary Password
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {confirmDialog.isOpen && (
        <ConfirmModal
          isOpen={confirmDialog.isOpen}
          title={confirmDialog.title}
          message={confirmDialog.message}
          onConfirm={confirmDialog.onConfirm || (() => {})}
          onCancel={() =>
            setConfirmDialog({
              isOpen: false,
              title: "",
              message: "",
              onConfirm: null,
            })
          }
          confirmText="Delete"
          variant="danger"
        />
      )}

      <TwoFactorModal
        isOpen={showTwoFactor}
        onClose={() => {
          setShowTwoFactor(false);
          loadData();
        }}
      />
    </div>
  );
}
