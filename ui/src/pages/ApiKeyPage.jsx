import { useState, useEffect, useMemo } from "react";
import { useLocalStorage } from "../hooks";
import PageHeader from "../components/ui/PageHeader";
import { Card, Input, Button, Select, Modal, Checkbox } from "../components/ui";
import ConfirmModal from "../components/ConfirmModal";
import { useAuth } from "../contexts/AuthContext";
import { useToast } from "../contexts/ToastContext";
import HelpTooltip from "../components/HelpTooltip";
import * as api from "../api";
import { OTLP_GATEWAY_HOST } from "../utils/constants";
import { buildOtelYaml } from "../utils/otelConfig";

export default function ApiKeyPage() {
  const { user, updateUser } = useAuth();
  const toast = useToast();
  const [orgId, setOrgId] = useState("");
  const [apiKeys, setApiKeys] = useState([]);

  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyValue, setNewKeyValue] = useState("");
  const [loading, setLoading] = useState(false);

  const [showKeyId, setShowKeyId] = useState(null);
  const [showDefaultModal, setShowDefaultModal] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [keyToDelete, setKeyToDelete] = useState(null);
  const [showShareModal, setShowShareModal] = useState(false);
  const [keyToShare, setKeyToShare] = useState(null);
  const [allUsers, setAllUsers] = useState([]);
  const [allGroups, setAllGroups] = useState([]);
  const [shareSearch, setShareSearch] = useState("");
  const [selectedShareUserIds, setSelectedShareUserIds] = useState([]);
  const [selectedShareGroupIds, setSelectedShareGroupIds] = useState([]);
  const [revealedOtlpTokens, setRevealedOtlpTokens] = useState({});
  const [showHidden, setShowHidden] = useState(false);
  const [apiKeyQuota, setApiKeyQuota] = useState(null);

  useEffect(() => {
    if (user) {
      if (!showHidden) {
        setApiKeys(user.api_keys || []);
      }
      setRevealedOtlpTokens((prev) => {
        const next = { ...prev };
        (user.api_keys || []).forEach((key) => {
          if (key?.id && key?.otlp_token) {
            next[key.id] = key.otlp_token;
          }
        });
        return next;
      });
      const defaultKey = (user.api_keys || []).find((k) => k.is_default);
      const orgKey =
        defaultKey || (user.api_keys || []).find((k) => k.key === user.org_id);
      setOrgId(orgKey?.id || "");
    }
  }, [user, showHidden]);

  const refreshUser = async () => {
    const [updatedUser, visibleKeys, displayKeys, quotaData] = await Promise.all([
      api.getCurrentUser(),
      api.listApiKeys().catch(() => null),
      api.listApiKeys({ showHidden }).catch(() => null),
      api.getSystemQuotas().catch(() => null),
    ]);
    const mergedUser = {
      ...updatedUser,
      api_keys: Array.isArray(visibleKeys)
        ? visibleKeys
        : (updatedUser.api_keys || []),
    };
    updateUser(mergedUser);
    setApiKeys(
      Array.isArray(displayKeys) ? displayKeys : (mergedUser.api_keys || []),
    );
    setApiKeyQuota(quotaData?.api_keys || null);
  };

  useEffect(() => {
    if (!user) return;
    refreshUser();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showHidden]);

  const inferSelectedGroupsFromShares = (
    key,
    users,
    groups,
    currentUserId,
    currentUserGroupIds,
  ) => {
    const sharedUserIds = new Set(
      (key?.shared_with || [])
        .map((item) => item?.user_id)
        .filter(Boolean)
        .map((id) => String(id)),
    );
    if (sharedUserIds.size === 0) return [];

    const myGroupIdSet = new Set((currentUserGroupIds || []).map((id) => String(id)));
    const eligibleGroups = (groups || []).filter((g) =>
      myGroupIdSet.has(String(g?.id || "")),
    );

    const inferred = [];
    for (const group of eligibleGroups) {
      const gid = String(group?.id || "");
      const members = (users || []).filter((u) => {
        const uid = String(u?.id || "");
        if (!uid || uid === String(currentUserId || "")) return false;
        const userGroupIds = (u?.group_ids || []).map((id) => String(id));
        return userGroupIds.includes(gid);
      });

      if (members.length === 0) continue;
      const allMembersShared = members.every((m) =>
        sharedUserIds.has(String(m?.id || "")),
      );
      if (allMembersShared) inferred.push(gid);
    }
    return inferred;
  };

  const handleSaveOrgId = async (e) => {
    if (e && typeof e.preventDefault === "function") e.preventDefault();
    setLoading(true);
    try {
      if (!orgId) {
        toast.error("Please select an API key");
        setLoading(false);
        return;
      }
      await api.updateApiKey(orgId, { is_default: true });
      await refreshUser();
      toast.success("Default API key updated successfully.");
      setShowDefaultModal(false);
    } catch (err) {
      const msg =
        err.body?.detail || err.message || "Failed to update default API key";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateKey = async (e) => {
    if (e && typeof e.preventDefault === "function") e.preventDefault();
    if (apiKeyQuota && apiKeyQuota.current >= apiKeyQuota.max) {
      toast.error(`Maximum API key limit reached (${apiKeyQuota.max})`);
      return;
    }
    if (!newKeyName.trim()) {
      toast.error("Key name is required");
      return;
    }
    setLoading(true);
    try {
      const created = await api.createApiKey({
        name: newKeyName.trim(),
        key: newKeyValue.trim() || undefined,
      });
      if (created?.id && created?.otlp_token) {
        setRevealedOtlpTokens((prev) => ({
          ...prev,
          [created.id]: created.otlp_token,
        }));
      }
      setNewKeyName("");
      setNewKeyValue("");
      await refreshUser();
      toast.success("API key created successfully.");
      setShowAddModal(false);
    } catch (err) {
      const msg = err.body?.detail || err.message || "Failed to create API key";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleActivateKey = async (key) => {
    try {
      await api.updateApiKey(key.id, { is_enabled: true });
      await refreshUser();
      toast.success("API key activated");
    } catch (err) {
      const msg = err.body?.detail || err.message || "Failed to update API key";
      toast.error(msg);
    }
  };

  const handleDeleteKey = async (key) => {
    try {
      await api.deleteApiKey(key.id);
      setRevealedOtlpTokens((prev) => {
        const next = { ...prev };
        delete next[key.id];
        return next;
      });
      await refreshUser();
      toast.success("API key deleted successfully.");
    } catch (err) {
      if (err?.status === 403) {
        toast.error("You are not authorized to delete this key");
        return;
      }
      const msg = err.body?.detail || err.message || "Failed to delete API key";
      toast.error(msg);
    }
  };

  const handleToggleHiddenKey = async (key) => {
    try {
      await api.setApiKeyHidden(key.id, !key.is_hidden);
      await refreshUser();
      toast.success(key.is_hidden ? "API key unhidden" : "API key hidden");
    } catch (err) {
      toast.error(err.body?.detail || err.message || "Failed to update API key visibility");
    }
  };

  const openShareModal = async (key) => {
    if (key?.is_default) {
      toast.error("Default key cannot be shared");
      return;
    }
    let users = allUsers;
    let groups = allGroups;
    if (!users.length) {
      try {
        const fetchedUsers = await api.getUsers();
        users = Array.isArray(fetchedUsers) ? fetchedUsers : [];
        setAllUsers(users);
      } catch {
        users = [];
        setAllUsers([]);
      }
    }
    if (!groups.length) {
      try {
        const fetchedGroups = await api.getGroups();
        groups = Array.isArray(fetchedGroups) ? fetchedGroups : [];
        setAllGroups(groups);
      } catch {
        groups = [];
        setAllGroups([]);
      }
    }

    const selectedUsers = (key?.shared_with || [])
      .map((item) => item.user_id)
      .filter(Boolean);
    const inferredGroups = inferSelectedGroupsFromShares(
      key,
      users,
      groups,
      user?.id,
      user?.group_ids || [],
    );

    setKeyToShare(key);
    setSelectedShareUserIds(selectedUsers);
    setSelectedShareGroupIds(inferredGroups);
    setShareSearch("");
    setShowShareModal(true);
  };

  const handleSaveShares = async () => {
    if (!keyToShare) return;
    if (keyToShare?.is_default) {
      toast.error("Default key cannot be shared");
      return;
    }
    setLoading(true);
    try {
      await api.replaceApiKeyShares(
        keyToShare.id,
        selectedShareUserIds,
        selectedShareGroupIds,
      );
      await refreshUser();
      toast.success("API key sharing updated");
      setShowShareModal(false);
      setKeyToShare(null);
      setSelectedShareUserIds([]);
      setSelectedShareGroupIds([]);
    } catch (err) {
      toast.error(
        err.body?.detail || err.message || "Failed to update API key sharing",
      );
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async (value, successMessage) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(successMessage);
    } catch (err) {
      const msg = "Failed to copy to clipboard";
      toast.error(msg);
    }
  };

  const handleDownloadYaml = (content) => {
    try {
      const blob = new Blob([content], { type: "text/yaml" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "otel-agent.yaml";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast.success("YAML downloaded");
    } catch (err) {
      const msg = "Failed to download YAML";
      toast.error(msg);
    }
  };

  const selectedOrgKeyValue = useMemo(() => {
    const found = apiKeys.find((k) => k.id === orgId);
    return found?.key || user?.org_id || "";
  }, [apiKeys, orgId, user]);
  const ownedApiKeys = useMemo(
    () => apiKeys.filter((k) => !k.is_shared),
    [apiKeys],
  );
  const maxApiKeys = apiKeyQuota?.max ?? null;
  const currentApiKeys = apiKeyQuota?.current ?? ownedApiKeys.length;
  const atApiKeyLimit =
    maxApiKeys !== null && Number(currentApiKeys) >= Number(maxApiKeys);

  const [showYamlModal, setShowYamlModal] = useState(false);
  const [yamlModalKeyId, setYamlModalKeyId] = useState("");
  // remember a custom host so users don't have to re-enter it every time
  const [gatewayHost, setGatewayHost] = useLocalStorage(
    "ApiKeyPage.gatewayHost",
    OTLP_GATEWAY_HOST,
  );

  const [yamlShowToken, setYamlShowToken] = useState(false);
  const [regeneratingToken, setRegeneratingToken] = useState(false);

  const yamlModalToken = useMemo(() => {
    const found = apiKeys.find((k) => k.id === yamlModalKeyId);
    return revealedOtlpTokens[yamlModalKeyId] || found?.otlp_token || "";
  }, [apiKeys, yamlModalKeyId, revealedOtlpTokens]);

  useEffect(() => {
    setYamlShowToken(false);
  }, [yamlModalKeyId, showYamlModal]);

  const derivedLoki = useMemo(
    () => `${gatewayHost.replace(/\/$/, "")}/loki/otlp`,
    [gatewayHost],
  );
  const derivedTempo = useMemo(
    () => `${gatewayHost.replace(/\/$/, "")}/tempo`,
    [gatewayHost],
  );
  const derivedMimir = useMemo(
    () => `${gatewayHost.replace(/\/$/, "")}/mimir/api/v1/push`,
    [gatewayHost],
  );

  const yamlModalContent = useMemo(
    () =>
      buildOtelYaml(yamlModalToken || "", {
        lokiEndpoint: derivedLoki,
        tempoEndpoint: derivedTempo,
        mimirEndpoint: derivedMimir,
      }),
    [yamlModalToken, derivedLoki, derivedTempo, derivedMimir],
  );

  const enabledCount = apiKeys.filter((k) => k.is_enabled).length;
  const activeOwnedKeyCandidate =
    ownedApiKeys.find((k) => k.is_enabled) ||
    ownedApiKeys.find((k) => k.is_default) ||
    ownedApiKeys[0] ||
    null;
  const isYamlKeyShared = Boolean(
    apiKeys.find((k) => k.id === yamlModalKeyId)?.is_shared,
  );
  const isYamlKeyDefault = Boolean(
    apiKeys.find((k) => k.id === yamlModalKeyId)?.is_default,
  );
  const canUseYaml = !isYamlKeyShared && Boolean(yamlModalToken);

  const handleRegenerateYamlToken = async () => {
    if (!yamlModalKeyId || isYamlKeyShared || isYamlKeyDefault) return;
    setRegeneratingToken(true);
    try {
      const updated = await api.regenerateApiKeyOtlpToken(yamlModalKeyId);
      const newToken = updated?.otlp_token || "";
      if (!newToken) {
        throw new Error("No OTLP token returned");
      }
      setRevealedOtlpTokens((prev) => ({
        ...prev,
        [yamlModalKeyId]: newToken,
      }));
      setYamlShowToken(true);
      await refreshUser();
      toast.success(
        "OTLP token regenerated. Update running OTEL agents with this new token.",
      );
    } catch (err) {
      toast.error(
        err.body?.detail || err.message || "Failed to regenerate OTLP token",
      );
    } finally {
      setRegeneratingToken(false);
    }
  };

  const filteredShareUsers = useMemo(() => {
    const q = shareSearch.trim().toLowerCase();
    if (!q) return allUsers;
    return allUsers.filter((u) =>
      [u.username, u.email, u.full_name, u.id].some((v) =>
        `${v || ""}`.toLowerCase().includes(q),
      ),
    );
  }, [allUsers, shareSearch]);

  const myShareableGroups = useMemo(() => {
    const myGroupIds = new Set(
      (Array.isArray(user?.group_ids) ? user.group_ids : []).map((id) =>
        String(id),
      ),
    );
    return allGroups.filter((group) => myGroupIds.has(String(group?.id || "")));
  }, [allGroups, user]);

  const getGroupMemberUserIds = (groupId) => {
    const gid = String(groupId || "");
    if (!gid) return [];
    return (allUsers || [])
      .filter((u) => String(u?.id || "") !== String(user?.id || ""))
      .filter((u) =>
        (u?.group_ids || []).map((id) => String(id)).includes(gid),
      )
      .map((u) => String(u.id));
  };

  const handleToggleShareGroup = (groupId) => {
    const gid = String(groupId || "");
    if (!gid) return;

    const memberIds = getGroupMemberUserIds(gid);
    const memberSet = new Set(memberIds);

    setSelectedShareGroupIds((prevGroups) => {
      const isSelected = prevGroups.includes(gid);
      const nextGroups = isSelected
        ? prevGroups.filter((id) => id !== gid)
        : [...prevGroups, gid];

      setSelectedShareUserIds((prevUsers) => {
        if (!isSelected) {
          return Array.from(new Set([...prevUsers, ...memberIds]));
        }

        const otherGroupIds = nextGroups;
        const usersCoveredByOtherGroups = new Set(
          otherGroupIds.flatMap((otherGid) => getGroupMemberUserIds(otherGid)),
        );

        return prevUsers.filter((uid) => {
          const suid = String(uid);
          if (!memberSet.has(suid)) return true;
          return usersCoveredByOtherGroups.has(suid);
        });
      });

      return nextGroups;
    });
  };

  function formatDisplayKey(key) {
    if (showKeyId === key.id) return key.key || "-";
    if (key.key) return `${key.key.slice(0, 6)}...${key.key.slice(-4)}`;
    return "-";
  }

  return (
    <div className="animate-fade-in max-w-7xl mx-auto">
      <PageHeader
        icon="key"
        title="API Keys"
        subtitle="Manage tenant keys for logs, traces and metrics. Use keys to isolate datasets per product or team."
      />

      <div className="space-y-8">
        <div>
          <Card className="p-3 rounded-lg border border-sre-border shadow-sm bg-sre-surface">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-sre-text">
                  Key Actions
                </h3>
                <p className="text-xs text-sre-text-muted mt-1">
                  Update the default API key, add a new key, or generate an OTEL
                  agent config.
                </p>
              </div>
              <div className="flex items-center gap-3">
                <Button
                  size="sm"
                  variant="secondary"
                  className="py-1 px-3"
                  onClick={() => setShowDefaultModal(true)}
                >
                  Update Default Key
                </Button>
                <Button
                  size="sm"
                  className="py-1 px-3"
                  onClick={() => setShowAddModal(true)}
                  disabled={atApiKeyLimit}
                  title={
                    atApiKeyLimit
                      ? `Maximum API key limit reached (${maxApiKeys})`
                      : "Add New Key"
                  }
                >
                  Add New Key
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  className="py-1 px-3"
                  onClick={() => {
                    if (!activeOwnedKeyCandidate) return;
                    setYamlModalKeyId(activeOwnedKeyCandidate.id);
                    setShowYamlModal(true);
                  }}
                  disabled={!activeOwnedKeyCandidate}
                  aria-disabled={!activeOwnedKeyCandidate}
                >
                  Generate Agent YAML
                </Button>
              </div>
            </div>
          </Card>
        </div>

        <Card
          title={`API Keys (${apiKeys.length})`}
          className="p-4 rounded-lg border border-sre-border shadow-sm bg-sre-surface"
        >
          <div className="flex justify-end mt-1">
            <label className="inline-flex items-center gap-2 text-xs text-sre-text-muted cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showHidden}
                onChange={(e) => setShowHidden(e.target.checked)}
                className="rounded border-sre-border"
              />
              Show hidden
            </label>
          </div>
          <p className="text-xs text-sre-text-muted mt-2">
            These API keys are local to your tenant and may be shared with other
            teams in your organization, since they scope to your tenant. Default
            keys cannot be shared.{" "}
            <strong>
              However, never share the OTLP token included in the generated OTEL
              Agent YAML — keep it secret.
            </strong>
          </p>
          <div className="mt-2 text-xs text-sre-text-muted">
            Capacity: <span className="font-medium text-sre-text">{currentApiKeys}</span>
            {" / "}
            <span className="font-medium text-sre-text">
              {maxApiKeys ?? "-"}
            </span>
            {" "}owned keys used.
          </div>
          {apiKeys.length === 0 ? (
            <div className="p-4 text-sm text-sre-text-muted">
              No API keys found.
            </div>
          ) : (
            <div className="mt-3 overflow-x-auto rounded-lg border border-sre-border bg-sre-surface/30">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="bg-sre-surface text-sre-text-muted text-xs uppercase tracking-wide">
                    <th className="px-4 py-3.5">
                      <span className="inline-flex items-center gap-1">
                        <span className="material-icons text-sm">label</span>
                        <span>Name</span>
                      </span>
                    </th>
                    <th className="px-4 py-3.5 border-l border-sre-border/50">
                      <span className="inline-flex items-center gap-1">
                        <span className="material-icons text-sm">key</span>
                        <span>Key</span>
                      </span>
                    </th>
                    <th className="px-4 py-3.5 border-l border-sre-border/50">
                      <span className="inline-flex items-center gap-1">
                        <span className="material-icons text-sm">verified</span>
                        <span>Status</span>
                      </span>
                    </th>
                    <th className="px-4 py-3.5 border-l border-sre-border/50">
                      <span className="inline-flex items-center gap-1">
                        <span className="material-icons text-sm">tune</span>
                        <span>Actions</span>
                      </span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {apiKeys.map((key) => (
                    <tr
                      key={key.id}
                      className="cursor-pointer align-top border-t border-sre-border/60 hover:bg-sre-background/70"
                      onClick={(e) => {
                        const interactiveTarget = e.target.closest(
                          "button, input, a, label",
                        );
                        if (interactiveTarget) return;
                        if (key.is_enabled) return;
                        if (key.is_shared && !key.can_use) return;
                        handleActivateKey(key);
                      }}
                    >
                      <td className="px-4 py-4">
                        <div className="font-medium text-sre-text">
                          {key.name}
                        </div>
                        {key.is_default && (
                          <div className="mt-1 inline-flex items-center gap-1 rounded-full border border-sre-border/60 bg-sre-surface-light px-2 py-0.5 text-[11px] font-medium text-sre-text">
                            <span className="material-icons text-xs">sell</span>
                            <span>Default key</span>
                          </div>
                        )}
                        {key.is_shared && key.owner_username && (
                          <div className="text-xs text-sre-text-muted">
                            Shared by {key.owner_username}
                          </div>
                        )}
                        {key.is_hidden && (
                          <div className="text-xs text-amber-600">Hidden</div>
                        )}
                        {!key.is_shared &&
                          Array.isArray(key.shared_with) &&
                          key.shared_with.length > 0 && (
                            <div className="text-xs text-sre-text-muted">
                              Shared with {key.shared_with.length} user
                              {key.shared_with.length === 1 ? "" : "s"}
                            </div>
                          )}
                      </td>
                      <td className="px-4 py-4 text-xs text-sre-text-muted break-all border-l border-sre-border/40">
                        <div className="flex items-center gap-3">
                          <div className="font-mono text-xs">
                            {formatDisplayKey(key)}
                          </div>
                          <div className="flex items-center gap-2">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() =>
                                setShowKeyId(
                                  showKeyId === key.id ? null : key.id,
                                )
                              }
                            >
                              {showKeyId === key.id ? "Hide" : "Show"}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() =>
                                handleCopy(
                                  key.key,
                                  "API key copied to clipboard",
                                )
                              }
                            >
                              Copy
                            </Button>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-4 border-l border-sre-border/40">
                        <div className="flex items-center gap-2">
                          <input
                            type="radio"
                            name="active-api-key"
                            className="h-4 w-4"
                            checked={key.is_enabled}
                            disabled={key.is_shared && !key.can_use}
                            onChange={() => handleActivateKey(key)}
                          />
                          <div className="text-sm">
                            {key.is_enabled ? (
                              <span className="text-green-600">Active</span>
                            ) : (
                              <span className="text-sre-text-muted">
                                Inactive
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-4 border-l border-sre-border/40">
                        <div className="flex items-center gap-4">
                          {!key.is_shared && !key.is_default && (
                            <button
                              type="button"
                              className="inline-flex items-center justify-center rounded p-1 text-sre-primary hover:bg-sre-primary/10 hover:text-sre-primary/80"
                              title="Share key"
                              aria-label={`Share ${key.name}`}
                              onClick={() => openShareModal(key)}
                            >
                              <span className="material-icons text-base">share</span>
                            </button>
                          )}
                          {!key.is_default && (
                            <button
                              type="button"
                              className="inline-flex items-center justify-center rounded p-1 text-red-500 hover:bg-red-500/10 hover:text-red-600"
                              title="Delete key"
                              aria-label={`Delete ${key.name}`}
                              onClick={() => {
                                setKeyToDelete(key);
                                setShowDeleteConfirm(true);
                              }}
                            >
                              <span className="material-icons text-base">delete</span>
                            </button>
                          )}
                          {key.is_shared && (
                            <button
                              type="button"
                              className="inline-flex items-center justify-center rounded p-1 text-sre-text-muted hover:bg-sre-border/40 hover:text-sre-text"
                              onClick={() => handleToggleHiddenKey(key)}
                              title={key.is_hidden ? "Unhide key" : "Hide key"}
                              aria-label={key.is_hidden ? `Unhide ${key.name}` : `Hide ${key.name}`}
                            >
                              <span className="material-icons text-base">
                                {key.is_hidden ? "visibility" : "visibility_off"}
                              </span>
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <ConfirmModal
          isOpen={showDeleteConfirm}
          title="Delete API Key"
          message={
            keyToDelete
              ? `Are you sure you want to delete the API key "${keyToDelete.name}"? This action cannot be undone. While you can create the same Org ID, you cannot create the same OTLP token, so ensure you know before expiring those OTEL agents.`
              : "Are you sure you want to delete this API key? This action cannot be undone. While you can create the same Org ID, you cannot create the same OTLP token, so ensure you know before expiring those OTEL agents."
          }
          onConfirm={async () => {
            if (keyToDelete) await handleDeleteKey(keyToDelete);
            setShowDeleteConfirm(false);
            setKeyToDelete(null);
          }}
          onCancel={() => {
            setShowDeleteConfirm(false);
            setKeyToDelete(null);
          }}
          confirmText="Delete"
          cancelText="Cancel"
          variant="danger"
        />

        {/* Default key modal */}
        <Modal
          isOpen={showDefaultModal}
          onClose={() => setShowDefaultModal(false)}
          title="Update Default API Key"
          size="md"
          closeOnOverlayClick={false}
        >
          <form
            onSubmit={handleSaveOrgId}
            className="space-y-4"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSaveOrgId(e);
              }
            }}
          >
            <Select
              value={orgId}
              onChange={(e) => setOrgId(e.target.value)}
              className="w-full"
              required
            >
              {apiKeys.length === 0 ? (
                <option value="">No API keys available</option>
              ) : (
                apiKeys.map((k) => (
                  <option key={k.id} value={k.id}>
                    {k.name} {k.is_default ? "(Default)" : ""}
                  </option>
                ))
              )}
            </Select>

            <div className="text-xs text-sre-text-muted">
              <strong>Note:</strong> This assigns the <em>default</em> API key —
              it is not the active key used for immediate viewing. Select the
              active key to change which product's data you are viewing; the
              default key is what will be recommended when creating Grafana
              datasources and similar integrations.
            </div>

            <div className="flex justify-end gap-3">
              <Button
                variant="ghost"
                onClick={() => setShowDefaultModal(false)}
              >
                Cancel
              </Button>
              <Button type="submit" loading={loading}>
                Save
              </Button>
            </div>
          </form>
        </Modal>
        <Modal
          isOpen={showAddModal}
          onClose={() => setShowAddModal(false)}
          title="Add API Key"
          size="md"
          closeOnOverlayClick={false}
        >
          <form
            onSubmit={handleCreateKey}
            className="space-y-4"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleCreateKey(e);
              }
            }}
          >
            <div>
              <div className="flex items-center justify-between">
                <label className="block text-sm font-medium text-sre-text mb-2">
                  Key Name
                </label>
                <HelpTooltip text="A descriptive name for this API key, e.g., the name of the application or service using it." />
              </div>
              <Input
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                placeholder="XYZ Product"
                required
              />
            </div>
            <div>
              <div className="flex items-center justify-between">
                <label className="block text-sm font-medium text-sre-text mb-2">
                  Key Value (optional)
                </label>
                <HelpTooltip text="The secret value for the API key. If left empty, a secure random value will be generated." />
              </div>
              <Input
                value={newKeyValue}
                onChange={(e) => setNewKeyValue(e.target.value)}
                placeholder="Leave empty to auto-generate"
              />
            </div>

            <div className="text-xs text-sre-text-muted">
              <strong>Note:</strong> This key is intended to be shared locally
              (on-premise) and is not the OTEL agent auth token. Your OTEL agent
              requires an OTLP auth token (e.g., <code>otel_auth_token</code>),
              which will be mapped to this API key.
            </div>

            <div className="flex justify-end gap-3">
              <Button variant="ghost" onClick={() => setShowAddModal(false)}>
                Cancel
              </Button>
              <Button
                type="submit"
                loading={loading}
                disabled={atApiKeyLimit}
                title={
                  atApiKeyLimit
                    ? `Maximum API key limit reached (${maxApiKeys})`
                    : "Create"
                }
              >
                Create
              </Button>
            </div>
          </form>
        </Modal>

        {/* YAML modal */}
        <Modal
          isOpen={showYamlModal}
          onClose={() => setShowYamlModal(false)}
          title="Generate OTEL Agent YAML"
          size="lg"
          closeOnOverlayClick={false}
        >
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <div className="flex items-center justify-between">
                  <label className="block text-sm font-medium text-sre-text mb-2">
                    Select API Key
                  </label>
                  <HelpTooltip text="Select the product or team this agent represents." />
                </div>
                <Select
                  value={yamlModalKeyId}
                  onChange={(e) => setYamlModalKeyId(e.target.value)}
                  className="w-full"
                >
                  {ownedApiKeys.map((k) => (
                    <option key={k.id} value={k.id}>
                      {k.name} {k.is_default ? "(Default)" : ""}
                    </option>
                  ))}
                </Select>
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="block text-sm font-medium text-sre-text mb-2">
                    OTLP Gateway Host
                  </label>
                  <HelpTooltip text="Enter the gateway host only, if you are running an otel collector locally, then localhost will work, or else you need the IP/domain of the place your Observantio is hosted" />
                </div>
                <Input
                  value={gatewayHost}
                  onChange={(e) => setGatewayHost(e.target.value)}
                  placeholder={OTLP_GATEWAY_HOST}
                />
                <p className="text-xs text-sre-text-muted mt-1">
                  Gateway host URL for OTLP endpoints.
                </p>
              </div>

              <div className="col-span-2">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-sre-text mb-2">
                    OTLP Token
                  </div>
                  <HelpTooltip text="This token will be sent as the 'x-otlp-token' HTTP header by exporters. Keep it secret." />
                </div>

                <div className="mt-1 p-2 bg-sre-background border border-sre-border rounded flex items-center justify-between gap-3">
                  <div className="font-mono text-xs truncate break-words">
                    {isYamlKeyShared
                      ? "OTLP token not available for shared keys"
                      : yamlModalToken
                        ? yamlShowToken
                          ? yamlModalToken
                          : `${yamlModalToken.slice(0, 6)}...${yamlModalToken.slice(-4)}`
                        : "No token available. Regenerate to reveal a new token."}
                  </div>
                  <div className="flex items-center gap-2">
                    {!isYamlKeyShared && (
                      <>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setYamlShowToken(!yamlShowToken)}
                          aria-label={
                            yamlShowToken ? "Hide token" : "Show token"
                          }
                          disabled={!yamlModalToken}
                        >
                          {yamlShowToken ? "Hide" : "Show"}
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() =>
                            handleCopy(
                              yamlModalToken || "",
                              "OTLP token copied to clipboard",
                            )
                          }
                          aria-label="Copy OTLP token"
                          disabled={!yamlModalToken}
                        >
                          Copy
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={handleRegenerateYamlToken}
                          loading={regeneratingToken}
                          aria-label="Regenerate OTLP token"
                          disabled={isYamlKeyDefault}
                        >
                          Regenerate
                        </Button>
                      </>
                    )}
                    {isYamlKeyShared && (
                      <div className="text-xs text-sre-text-muted">
                        Token hidden — contact owner to obtain agent config.
                      </div>
                    )}
                  </div>
                </div>

                <div className="text-xs text-sre-text-muted mt-2">
                  Secure OTLP Gateway: the gateway validates the token and maps
                  it to the tenant (X-Scope-OrgID). Do not expose raw org keys.
                  {isYamlKeyDefault
                    ? " Default key OTLP token regeneration is disabled by policy."
                    : ""}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                onClick={() =>
                  handleCopy(yamlModalContent, "OTEL YAML copied to clipboard")
                }
                aria-label="Copy YAML"
                disabled={!canUseYaml}
              >
                <span className="material-icons mr-2">content_copy</span>Copy
                YAML
              </Button>
              <Button
                variant="secondary"
                onClick={() => handleDownloadYaml(yamlModalContent)}
                aria-label="Download YAML"
                disabled={!canUseYaml}
              >
                <span className="material-icons mr-2">download</span>Download
                YAML
              </Button>
              <div className="text-xs text-sre-text-muted ml-auto">
                sudo otelcol-contrib --config otel.yaml
              </div>
            </div>

            <div className="bg-sre-background p-3 rounded border border-sre-border text-xs overflow-auto max-h-72">
              <pre className="whitespace-pre-wrap break-words text-sre-text">
                <code>{yamlModalContent}</code>
              </pre>
            </div>
          </div>
        </Modal>

        <Modal
          isOpen={showShareModal}
          onClose={() => {
            setShowShareModal(false);
            setSelectedShareGroupIds([]);
          }}
          title={`Share API Key${keyToShare ? `: ${keyToShare.name}` : ""}`}
          size="lg"
          closeOnOverlayClick={false}
        >
          <div className="space-y-4">
            <div className="text-xs text-sre-text-muted">
              Select users who can view and use this key. Owner retains
              edit/delete control.
            </div>
            <div className="p-3 rounded border border-sre-border bg-sre-background">
              <div className="text-xs font-medium text-sre-text mb-2">
                Share with groups you are in
              </div>
              {myShareableGroups.length > 0 ? (
                <div className="space-y-2 max-h-32 overflow-auto">
                  {myShareableGroups.map((group) => (
                    <div
                      key={group.id}
                      className="flex items-center justify-between p-2 rounded hover:bg-sre-surface/50"
                    >
                      <div className="text-sm text-sre-text">{group.name}</div>
                      <Checkbox
                        checked={selectedShareGroupIds.includes(group.id)}
                        onChange={() => handleToggleShareGroup(group.id)}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-sre-text-muted">
                  No eligible groups found.
                </div>
              )}
            </div>
            <Input
              value={shareSearch}
              className="text-sm"
              onChange={(e) => setShareSearch(e.target.value)}
              placeholder="Search by username or email"
            />

            <div className="max-h-64 overflow-auto ">
              {filteredShareUsers
                .filter((u) => u.id !== user?.id)
                .map((u) => (
                  <div
                    key={u.id}
                    className="flex items-center justify-between p-2 rounded hover:bg-sre-surface/50"
                  >
                    <div className="text-sm text-sre-text">
                      {u.username} {u.email ? `<${u.email}>` : ""}
                    </div>
                    <Checkbox
                      checked={selectedShareUserIds.includes(u.id)}
                      onChange={() =>
                        setSelectedShareUserIds((prev) =>
                          prev.includes(u.id)
                            ? prev.filter((id) => id !== u.id)
                            : [...prev, u.id],
                        )
                      }
                    />
                  </div>
                ))}
              {filteredShareUsers.filter((u) => u.id !== user?.id).length ===
                0 && (
                <div className="p-2 text-sm text-sre-text-muted">
                  No users found.
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2">
              <Button
                variant="ghost"
                onClick={() => {
                  setShowShareModal(false);
                  setSelectedShareGroupIds([]);
                }}
              >
                Cancel
              </Button>
              <Button onClick={handleSaveShares} loading={loading}>
                Save
              </Button>
            </div>
          </div>
        </Modal>
      </div>
    </div>
  );
}
