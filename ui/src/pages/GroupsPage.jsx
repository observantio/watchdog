import { useState, useEffect, useCallback } from "react";
import {
  Card,
  Button,
  Input,
  Modal,
  ConfirmDialog,
  Alert,
} from "../components/ui";
import { useNavigate } from "react-router-dom";
import { usePermissions } from "../hooks/usePermissions";
import { useToast } from "../contexts/ToastContext";
import { useAuth } from "../contexts/AuthContext";
import HelpTooltip from "../components/HelpTooltip";
import MemberList from "../components/groups/MemberList";
import RuleEditorWizard from "../components/alertmanager/RuleEditorWizard";
import GroupForm from "../components/groups/GroupForm";
import GroupPermissions from "../components/groups/GroupPermissions";
import GroupCard from "../components/groups/GroupCard";
import {
  groupPermissionsByResource,
  filterGroups,
  sortUsersByDisplayName,
} from "../utils/groupManagementUtils";
import * as api from "../api";

export default function GroupsPage() {
  const { canManageGroups } = usePermissions();
  const { user } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [groups, setGroups] = useState([]);
  const [users, setUsers] = useState([]);
  const [permissions, setPermissions] = useState([]);
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [saving, setSaving] = useState(false);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showPermissionsModal, setShowPermissionsModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  const [formData, setFormData] = useState({ name: "", description: "" });
  const [editGroupData, setEditGroupData] = useState({
    id: "",
    name: "",
    description: "",
  });
  const [groupPermissions, setGroupPermissions] = useState([]);
  const [selectedMembers, setSelectedMembers] = useState([]);

  const [currentStep, setCurrentStep] = useState(0);
  const totalSteps = 3;
  const canProceedToNextStep = () => {
    if (currentStep === 0) return !!formData.name.trim();
    return true;
  };
  const handleNext = () => {
    if (canProceedToNextStep() && currentStep < totalSteps - 1)
      setCurrentStep((s) => s + 1);
  };
  const handlePrevious = () => {
    if (currentStep > 0) setCurrentStep((s) => s - 1);
  };
  const handleStepClick = (stepIndex) => {
    if (typeof stepIndex !== "number") return;
    if (stepIndex < 0 || stepIndex > totalSteps - 1) return;
    setCurrentStep(stepIndex);
  };
  const handleWizardSubmit = async () => {
    await createGroup();
  };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [groupsData, permsData] = await Promise.all([
        api.getGroups(),
        api.getPermissions(),
      ]);
      setGroups(groupsData);
      setPermissions(permsData);
      const usersData = await api.getUsers().catch(() => []);
      setUsers(usersData || []);
    } catch (err) {
      toast.error("Failed to load groups: " + err.message);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const createGroup = async () => {
    if (!formData.name.trim()) {
      toast.error("Group name is required");
      return;
    }

    setSaving(true);
    let createdGroupId = null;
    try {
      const newGroup = await api.createGroup(formData);
      createdGroupId = newGroup?.id || null;
      if (groupPermissions?.length > 0) {
        await api.updateGroupPermissions(newGroup.id, groupPermissions);
      }
      const creatorId = String(user?.id || user?.user_id || "").trim();
      const membersWithOwner = Array.from(
        new Set([
          ...selectedMembers.map((id) => String(id || "").trim()).filter(Boolean),
          ...(creatorId ? [creatorId] : []),
        ]),
      );
      await api.updateGroupMembers(newGroup.id, membersWithOwner);

      toast.success("Group created successfully");
      setShowCreateModal(false);
      setCurrentStep(0);
      setFormData({ name: "", description: "" });
      setGroupPermissions([]);
      setSelectedMembers([]);
      await fetchData();
    } catch (err) {
      if (createdGroupId) {
        try {
          await api.deleteGroup(createdGroupId);
        } catch (_) {
          // ignore rollback failures; surface original create flow error
        }
      }
      toast.error("Failed to create group: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  const deleteGroup = async (groupId) => {
    try {
      await api.deleteGroup(groupId);
      toast.success("Group deleted successfully");
      fetchData();
    } catch (err) {
      toast.error("Failed to delete group: " + err.message);
    }
  };

  const openPermissionsModal = (group) => {
    setSelectedGroup(group);
    const currentPerms = group.permissions?.map((p) => p.name || p) || [];
    setGroupPermissions(currentPerms);
    const memberIds = (users || [])
      .filter((u) => (u.group_ids || []).includes(group.id))
      .map((u) => u.id);
    setSelectedMembers(memberIds);
    setShowPermissionsModal(true);
  };

  const openEditModal = (group) => {
    setEditGroupData({
      id: group.id,
      name: group.name || "",
      description: group.description || "",
    });
    const memberIds = (users || [])
      .filter((u) => (u.group_ids || []).includes(group.id))
      .map((u) => u.id);
    setSelectedMembers(memberIds);
    setShowEditModal(true);
  };

  const savePermissions = async () => {
    setSaving(true);
    try {
      await api.updateGroupPermissions(selectedGroup.id, groupPermissions);
      await api.updateGroupMembers(selectedGroup.id, selectedMembers);
      toast.success("Permissions updated successfully");
      setShowPermissionsModal(false);
      setSelectedGroup(null);
      setSelectedMembers([]);
      await fetchData();
    } catch (err) {
      toast.error("Failed to update permissions: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  const closeCreateModal = () => {
    setShowCreateModal(false);
    setFormData({ name: "", description: "" });
    setGroupPermissions([]);
    setSelectedMembers([]);
    setCurrentStep(0);
  };

  const closeEditModal = () => {
    setShowEditModal(false);
    setEditGroupData({ id: "", name: "", description: "" });
    setSelectedMembers([]);
  };

  const updateGroup = async () => {
    if (!editGroupData.name.trim()) {
      toast.error("Group name is required");
      return;
    }

    setSaving(true);
    try {
      await api.updateGroup(editGroupData.id, {
        name: editGroupData.name,
        description: editGroupData.description,
      });
      await api.updateGroupMembers(editGroupData.id, selectedMembers);
      toast.success("Group updated successfully");
      closeEditModal();
      await fetchData();
    } catch (err) {
      toast.error("Failed to update group: " + err.message);
    } finally {
      setSaving(false);
    }
  };

  const togglePermission = (permName) => {
    setGroupPermissions((prev) =>
      prev.includes(permName)
        ? prev.filter((p) => p !== permName)
        : [...prev, permName],
    );
  };

  const addPerms = (perms) => {
    const permNames = new Set(perms.map((p) => p.name));
    setGroupPermissions((prev) => Array.from(new Set([...prev, ...permNames])));
  };

  const removePerms = (perms) => {
    const permNames = new Set(perms.map((p) => p.name));
    setGroupPermissions((prev) => prev.filter((p) => !permNames.has(p)));
  };

  const toggleMember = (userId) => {
    setSelectedMembers((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return Array.from(next);
    });
  };

  const filteredGroups = filterGroups(groups, searchQuery);
  const sortedUsers = sortUsersByDisplayName(users);
  const permissionsByResource = groupPermissionsByResource(permissions);

  if (!canManageGroups) {
    return (
      <div className="p-6">
        <Alert variant="error">
          <div className="font-semibold">Access Denied</div>
          <div className="text-sm mt-1">
            You don't have permission to manage groups.
          </div>
        </Alert>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-sre-text">
            Groups Management
          </h1>
          <p className="text-sre-text-muted mt-2">
            Manage groups and assign permissions that members will inherit
          </p>
        </div>
        <div className="flex items-center gap-2">
          {!(groups.length === 0 && !searchQuery) && (
            <Button onClick={() => setShowCreateModal(true)} size="sm">
              <span className="material-icons mr-2">add</span>
              Create Group
            </Button>
          )}
          <Button
            size="sm"
            variant="secondary"
            onClick={() => navigate("/users")}
          >
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
        <div className="grid gap-6 grid-cols-1 md:grid-cols-2">
          {filteredGroups.map((group) => {
            const usersCount = (users || []).filter((u) =>
              (u.group_ids || []).includes(group.id),
            ).length;
            const permsCount = (group.permissions || []).length || 0;
            return (
              <GroupCard
                key={group.id}
                group={group}
                usersCount={usersCount}
                permsCount={permsCount}
                onOpenPermissions={openPermissionsModal}
                onEdit={openEditModal}
                onDelete={setDeleteConfirm}
              />
            );
          })}
        </div>
      )}

      {filteredGroups.length === 0 && !loading && (
        <Card className="text-center py-12">
          <svg
            className="w-16 h-16 mx-auto text-sre-text-muted mb-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
            />
          </svg>
          <h3 className="text-lg font-semibold text-sre-text mb-2">
            {searchQuery ? "No groups found" : "No groups yet"}
          </h3>
          <p className="text-sre-text-muted mb-4">
            {searchQuery
              ? "Try a different search term"
              : "Create your first group to organize users and permissions"}
          </p>
          {!searchQuery && (
            <Button onClick={() => setShowCreateModal(true)}>
              Create Group
            </Button>
          )}
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
          <div className="flex items-center justify-between w-full">
            <div>
              <Button
                variant="ghost"
                onClick={closeCreateModal}
                disabled={saving}
              >
                Cancel
              </Button>
            </div>
            <div className="w-1/2">
              <RuleEditorWizard
                currentStep={currentStep}
                totalSteps={totalSteps}
                onNext={handleNext}
                onPrevious={handlePrevious}
                onSubmit={handleWizardSubmit}
                onStepClick={handleStepClick}
                canProceed={canProceedToNextStep()}
                isSubmitting={saving}
                hasErrors={false}
                showIndicator={false}
              />
            </div>
          </div>
        }
      >
        <div className="space-y-6">
          <RuleEditorWizard
            currentStep={currentStep}
            totalSteps={totalSteps}
            onNext={handleNext}
            onPrevious={handlePrevious}
            onSubmit={handleWizardSubmit}
            onStepClick={handleStepClick}
            canProceed={canProceedToNextStep()}
            isSubmitting={saving}
            hasErrors={false}
            showButtons={false}
            steps={[
              {
                key: "details",
                label: "Group Details",
                icon: "groups",
                description: "Name & description",
              },
              {
                key: "permissions",
                label: "Permissions",
                icon: "security",
                description: "Select action-level permissions",
              },
              {
                key: "members",
                label: "Members",
                icon: "person",
                description: "Add members (optional)",
              },
            ]}
          />

          {/* Step 1 — Group Details */}
          {currentStep === 0 && (
            <GroupForm formData={formData} setFormData={setFormData} />
          )}

          {/* Step 2 — Permissions */}
          {currentStep === 1 && (
            <GroupPermissions
              permissionsByResource={permissionsByResource}
              groupPermissions={groupPermissions}
              togglePermission={togglePermission}
              addPerms={addPerms}
              removePerms={removePerms}
            />
          )}

          {/* Step 3 — Members */}
          {currentStep === 2 && (
            <div className="space-y-4">
              <h3 className="font-semibold text-sre-text">
                Group Members (Optional)
              </h3>
              <MemberList
                users={sortedUsers}
                selectedMembers={selectedMembers}
                toggleMember={toggleMember}
              />
            </div>
          )}
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
            <Button
              onClick={updateGroup}
              disabled={!editGroupData.name.trim() || saving}
            >
              {saving ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        }
      >
        <div className="space-y-6">
          <div className="text-sm text-sre-text-muted">
            Update group name and description. Permissions can be edited in the
            Permissions dialog.
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <GroupForm
              formData={editGroupData}
              setFormData={setEditGroupData}
            />
          </div>
          <div className="space-y-3">
            <h3 className="font-semibold text-sre-text">Group Members</h3>
            <MemberList
              users={sortedUsers}
              selectedMembers={selectedMembers}
              toggleMember={toggleMember}
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
              {saving ? "Saving..." : "Save Permissions"}
            </Button>
          </div>
        }
      >
        <div className="space-y-6">
          <Alert variant="info">
            <div className="text-sm">
              All members of this group will inherit these permissions.
              User-specific permissions override group permissions.
            </div>
          </Alert>

          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-sre-text">Group Members</h3>
              <HelpTooltip text="Users who are members of this group and will inherit the selected permissions." />
            </div>
            <MemberList
              users={sortedUsers}
              selectedMembers={selectedMembers}
              toggleMember={toggleMember}
            />
          </div>

          <div className="flex items-center">
            <div className="flex items-center gap-2">
              <div className="text-sm text-sre-text-muted">
                {groupPermissions.length} permission
                {groupPermissions.length === 1 ? "" : "s"} selected
              </div>
              <HelpTooltip text="Total number of permissions currently assigned to this group." />
            </div>
          </div>

          <GroupPermissions
            permissionsByResource={permissionsByResource}
            groupPermissions={groupPermissions}
            togglePermission={togglePermission}
            addPerms={addPerms}
            removePerms={removePerms}
          />
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
