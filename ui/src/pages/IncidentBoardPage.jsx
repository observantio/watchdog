import { useState, useEffect, useMemo, useCallback, memo } from "react";

export function getUserLabel(userItem) {
  if (!userItem) return "Unknown user";
  const name = userItem.full_name || userItem.username || userItem.id || "";
  const email = userItem.email ? ` ${userItem.email}` : "";
  return `${name}${email}`;
}

function looksLikeUuid(value) {
  const s = String(value || "").trim();
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
    s,
  );
}

function getIncidentAssigneeLabel(incident, userById = {}, currentUser = null) {
  const assignee = String(incident?.assignee || "").trim();
  if (!assignee) return "Unassigned";

  const mapped = userById[assignee];
  if (mapped) return getUserLabel(mapped);

  const explicitName =
    incident?.assignee_username ||
    incident?.assigneeUsername ||
    incident?.assignee_name ||
    incident?.assigneeName ||
    "";
  if (String(explicitName || "").trim()) return String(explicitName).trim();

  const currentUserId = String(
    currentUser?.id || currentUser?.user_id || "",
  ).trim();
  if (currentUserId && assignee === currentUserId) {
    return getUserLabel(currentUser);
  }

  return looksLikeUuid(assignee) ? "Unknown user" : assignee;
}

function getIncidentCorrelationId(incident) {
  if (!incident || typeof incident !== "object") return "";

  const direct = [
    incident.correlationId,
    incident.correlation_id,
    incident.group,
    incident.alertgroup,
  ];
  for (const value of direct) {
    const s = String(value || "").trim();
    if (s) return s;
  }

  const sources = [incident.labels, incident.annotations];
  const keys = [
    "beobservantCorrelationId",
    "correlation_id",
    "correlationId",
    "group",
    "alertgroup",
  ];
  for (const source of sources) {
    if (!source || typeof source !== "object") continue;
    for (const key of keys) {
      const s = String(source[key] || "").trim();
      if (s) return s;
    }
  }
  return "";
}

function getIncidentLabelEntries(incident) {
  if (!incident || typeof incident !== "object") return [];
  const labels = incident.labels;
  if (!labels || typeof labels !== "object") return [];
  const nextLabels = { ...labels };
  const metricStates = String(
    incident?.annotations?.beobservantMetricStates || "",
  ).trim();
  if (metricStates) {
    nextLabels.state = metricStates;
  }
  return Object.entries(nextLabels)
    .filter(([key, value]) => String(key || "").trim() && value !== null && typeof value !== "undefined")
    .sort(([a], [b]) => String(a).localeCompare(String(b)));
}

function escapeRegExp(value) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

import {
  updateIncident,
  getGroups,
  createIncidentJira,
  listJiraProjectsByIntegration,
  listJiraIssueTypes,
  listIncidentJiraComments,
  listJiraIntegrations,
  getIncidentsSummary,
  getAlertsByFilter,
} from "../api";
import {
  Card,
  Button,
  Select,
  Badge,
  Spinner,
  Modal,
  Input,
  Alert,
} from "../components/ui";
import { useToast } from "../contexts/ToastContext";
import { useAuth } from "../contexts/AuthContext";
import HelpTooltip from "../components/HelpTooltip";
import { useIncidentsData, useLocalStorage } from "../hooks";

export function clearDroppedState(prev, droppedId) {
  if (
    typeof droppedId === "undefined" ||
    droppedId === null ||
    droppedId === ""
  )
    return prev;
  const next = { ...prev };
  delete next[droppedId];
  return next;
}

const IncidentCard = memo(function IncidentCard({
  incident,
  columnKey,
  canUpdateIncidents,
  userById,
  currentUser,
  onOpenModal,
  onSetModalTab,
  onQuickResolve,
  onUnhide,
  onHide,
  droppingState,
  compact = false,
}) {
  const assigneeLabel = getIncidentAssigneeLabel(incident, userById, currentUser);
  const correlationId = getIncidentCorrelationId(incident);
  const previewLabels = getIncidentLabelEntries(incident).slice(0, 3);

  return (
    <div
      draggable={!!canUpdateIncidents}
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/incident", String(incident.id));
        e.currentTarget.classList.add("opacity-50", "scale-95", "rotate-2");
      }}
      onDragEnd={(e) => {
        e.currentTarget.classList.remove("opacity-50", "scale-95", "rotate-2");
      }}
      className={`group bg-gradient-to-br from-sre-bg to-sre-surface border border-sre-border/50 rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 cursor-move relative overflow-hidden backdrop-blur-sm ${
        compact ? "min-h-[140px]" : ""
      }`}
    >
      <div
        className={`h-2 w-full ${
          incident.severity === "critical"
            ? "bg-gradient-to-r from-red-500 to-red-600"
            : incident.severity === "warning"
              ? "bg-gradient-to-r from-yellow-500 to-orange-500"
              : "bg-gradient-to-r from-blue-500 to-blue-600"
        }`}
      />

      <div className={compact ? "p-3" : "p-5"}>
        <div className={`flex items-start justify-between gap-4 ${compact ? "mb-2" : "mb-4"}`}>
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div
              className={`w-3 h-3 rounded-full flex-shrink-0 ${
                incident.severity === "critical"
                  ? "bg-red-500 shadow-red-500/50 shadow-lg"
                  : incident.severity === "warning"
                    ? "bg-yellow-500 shadow-yellow-500/50 shadow-lg"
                    : "bg-blue-500 shadow-blue-500/50 shadow-lg"
              }`}
            />
            <h3 className={`font-semibold text-sre-text leading-tight flex-1 min-w-0 truncate ${compact ? "text-sm" : "text-base"}`}>
              {incident.alertName}
            </h3>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <Badge
              variant={incident.status === "resolved" ? "success" : "warning"}
              className="text-xs px-3 py-1.5 rounded-full font-medium shadow-sm"
            >
              {incident.status}
            </Badge>
          </div>
        </div>

        <div className={`${compact ? "space-y-2 mb-2" : "space-y-3 mb-4"}`}>
          {(correlationId || previewLabels.length > 0) && (
            <div className="flex items-center gap-2 text-xs flex-wrap">
              {correlationId && (
                <Badge variant="ghost" className="max-w-full truncate">
                  Correlation: {correlationId}
                </Badge>
              )}
              {!compact &&
                previewLabels.map(([key, value]) => (
                <Badge
                  key={`${incident.id}-label-${key}`}
                  variant="ghost"
                  className="max-w-full truncate"
                >
                  {key}: {String(value)}
                </Badge>
                ))}
            </div>
          )}

          <div className="flex items-center gap-3 text-sm text-sre-text-muted">
            <div className="flex items-center gap-2">
              <span className="material-icons text-base text-sre-primary/70">
                schedule
              </span>
              <span className="font-medium">
                {new Date(incident.lastSeenAt).toLocaleString()}
              </span>
            </div>
          </div>

          {!compact && (
            <div className="flex items-center gap-3 text-sm text-sre-text-muted min-w-0">
              <div className="flex items-center gap-2 min-w-0">
                <span className="material-icons text-base text-sre-primary/70">
                  person
                </span>
                <span className="font-medium truncate min-w-0 max-w-full">
                  {assigneeLabel}
                </span>
              </div>
            </div>
          )}

          {!compact && incident.jiraTicketKey && (
            <div className="flex items-center gap-3 text-sm text-sre-text-muted">
              <div className="flex items-center gap-2">
                <span className="material-icons text-base text-sre-primary/70">
                  link
                </span>
                <span className="font-medium text-sre-primary hover:text-sre-primary/80 transition-colors truncate">
                  {incident.jiraTicketKey}
                </span>
              </div>
            </div>
          )}
        </div>

        <div className={`flex items-center justify-between ${compact ? "mb-2" : "mb-4"}`}>
          <div className="flex items-center gap-2 flex-wrap">
            <Badge
              variant={
                incident.severity === "critical"
                  ? "error"
                  : incident.severity === "warning"
                    ? "warning"
                    : "info"
              }
              className="text-xs px-3 py-1.5 rounded-full font-medium shadow-sm"
            >
              <span className="material-icons text-sm mr-1">
                {incident.severity === "critical"
                  ? "error"
                  : incident.severity === "warning"
                    ? "warning"
                    : "info"}
              </span>
              {incident.severity}
            </Badge>

            {incident.hideWhenResolved && (
              <Badge
                variant="ghost"
                className="whitespace-nowrap text-xs px-3 py-1.5 rounded-full border border-sre-border/50 bg-sre-surface/50"
              >
                <span className="material-icons text-sm mr-1">
                  visibility_off
                </span>
                Hidden
              </Badge>
            )}
          </div>

          <div className="flex items-center gap-1">
            {canUpdateIncidents && columnKey === "unassigned" && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  onOpenModal(incident);
                  onSetModalTab("assignment");
                }}
                className="transition-all duration-200 p-2 h-8 w-8 hover:bg-sre-surface/50"
                title="Quick assign"
              >
                <span className="material-icons text-sm">person_add</span>
              </Button>
            )}

            {canUpdateIncidents &&
              columnKey === "assigned" &&
              incident.status !== "resolved" && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => onQuickResolve(incident)}
                  className="transition-all duration-200 p-2 h-8 w-8 hover:bg-sre-surface/50"
                  title="Quick resolve"
                >
                  <span className="material-icons text-sm">task_alt</span>
                </Button>
              )}

            {incident.status === "resolved" && incident.hideWhenResolved && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => onUnhide(incident.id)}
                className="opacity-0 group-hover:opacity-100 transition-all duration-200 p-2 h-8 w-8 hover:bg-sre-surface/50"
                title="Unhide incident"
              >
                <span className="material-icons text-sm">visibility</span>
              </Button>
            )}

            {canUpdateIncidents &&
              incident.status === "resolved" &&
              !incident.hideWhenResolved && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => onHide(incident.id)}
                  className="opacity-0 group-hover:opacity-100 transition-all duration-200 p-2 h-8 w-8 hover:bg-sre-surface/50"
                  title="Hide incident"
                >
                  <span className="material-icons text-sm">visibility_off</span>
                </Button>
              )}

            {!compact && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                onOpenModal(incident);
                onSetModalTab("jira");
              }}
              className="opacity-0 group-hover:opacity-100 transition-all duration-200 p-2 h-8 w-8 hover:bg-sre-surface/50"
              title="Jira"
            >
              <span className="material-icons text-sm">link</span>
            </Button>
            )}

            {!compact && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                onOpenModal(incident);
                onSetModalTab("notes");
              }}
              className="opacity-0 group-hover:opacity-100 transition-all duration-200 p-2 h-8 w-8 hover:bg-sre-surface/50 relative"
              title="View notes"
            >
              <span className="material-icons text-sm">notes</span>
              {Array.isArray(incident.notes) && incident.notes.length > 0 && (
                <span className="absolute -top-1 -right-1 inline-flex items-center justify-center px-1.5 py-0.5 text-xs rounded-full bg-sre-primary text-white">
                  {incident.notes.length}
                </span>
              )}
            </Button>
            )}

            <Button
              size="sm"
              variant="ghost"
              onClick={() => onOpenModal(incident)}
              className="opacity-0 group-hover:opacity-100 transition-all duration-200 p-2 h-8 w-8 hover:bg-sre-surface/50"
            >
              <span className="material-icons text-sm">edit</span>
            </Button>
          </div>
        </div>
      </div>

      <div className={`absolute ${compact ? "top-2 left-2" : "top-3 left-3"} opacity-0 group-hover:opacity-100 transition-opacity duration-200`}>
        <span className="material-icons text-sre-text-muted/70 text-sm">
          drag_indicator
        </span>
      </div>

      {droppingState && (
        <div className="absolute inset-0 bg-sre-bg-card/90 backdrop-blur-md flex items-center justify-center rounded-xl border-2 border-sre-primary/30">
          <div className="flex items-center gap-3 text-sre-primary">
            <Spinner size="sm" />
            <span className="text-sm font-semibold">Updating...</span>
          </div>
        </div>
      )}
    </div>
  );
});

const Column = memo(function Column({
  title,
  count,
  colorDot,
  icon,
  help,
  items,
  empty,
  canUpdateIncidents,
  onDropColumn,
  userById,
  currentUser,
  openIncidentModal,
  setIncidentModalTab,
  onQuickResolve,
  handleUnhideIncident,
  handleHideIncident,
  dropping,
  hiddenResolvedItems = [],
  hiddenResolvedVisibleCount = 0,
  onLoadMoreHiddenResolved = null,
}) {
  const visibleHiddenResolved = hiddenResolvedItems.slice(
    0,
    hiddenResolvedVisibleCount,
  );
  const hasMoreHiddenResolved =
    hiddenResolvedItems.length > visibleHiddenResolved.length;

  return (
    <div className="flex flex-col">
      <div className="mb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 ${colorDot} rounded-full`} />
            <h3 className="text-lg font-semibold text-sre-text">{title}</h3>
            <HelpTooltip text={help} />
            <span className="px-2 py-1 bg-sre-surface text-sre-text-muted text-xs font-medium rounded-full border border-sre-border">
              {count}
            </span>
          </div>
        </div>
        <div
          className={`mt-2 h-1 ${colorDot.replace("bg-", "bg-gradient-to-r from-") || "bg-gradient-to-r from-blue-500 to-blue-400"} rounded-full`}
        />
      </div>
      <div
        className={`flex-1 min-h-[500px] p-4 rounded-xl border-2 border-dashed border-sre-border/50 bg-sre-surface/30 transition-all duration-200 ${
          canUpdateIncidents
            ? "hover:border-sre-primary/30 hover:bg-sre-surface/50 cursor-move"
            : ""
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = "move";
        }}
        onDrop={(e) => {
          onDropColumn(icon, e);
        }}
      >
        <div className="space-y-3">
          {items.length > 0 ? (
            items.map((it) => (
              <IncidentCard
                key={it.id}
                incident={it}
                columnKey={icon}
                canUpdateIncidents={canUpdateIncidents}
                userById={userById}
                currentUser={currentUser}
                onOpenModal={openIncidentModal}
                onSetModalTab={setIncidentModalTab}
                onQuickResolve={onQuickResolve}
                onUnhide={handleUnhideIncident}
                onHide={handleHideIncident}
                droppingState={!!dropping[it.id]}
              />
            ))
          ) : icon === "resolved" && hiddenResolvedItems.length > 0 ? null : (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <span className="material-icons text-4xl text-sre-text-muted/50 mb-3">
                {empty.icon}
              </span>
              <p className="text-sre-text-muted text-sm">{empty.title}</p>
              <p className="text-sre-text-muted/70 text-xs mt-1">
                {empty.subtitle}
              </p>
            </div>
          )}

          {icon === "resolved" && hiddenResolvedItems.length > 0 && (
            <div className="mt-4 border-t border-sre-border/60 pt-4">
              <div className="flex items-center justify-between mb-3">
                <div className="text-xs uppercase tracking-wide text-sre-text-muted">
                  Hidden Resolved ({hiddenResolvedItems.length})
                </div>
                <HelpTooltip text="Hidden resolved incidents are compacted. Load more to view additional hidden cards." />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {visibleHiddenResolved.map((it) => (
                  <IncidentCard
                    key={`hidden-${it.id}`}
                    incident={it}
                    columnKey={icon}
                    canUpdateIncidents={canUpdateIncidents}
                    userById={userById}
                    currentUser={currentUser}
                    onOpenModal={openIncidentModal}
                    onSetModalTab={setIncidentModalTab}
                    onQuickResolve={onQuickResolve}
                    onUnhide={handleUnhideIncident}
                    onHide={handleHideIncident}
                    droppingState={!!dropping[it.id]}
                    compact
                  />
                ))}
              </div>
              {hasMoreHiddenResolved && (
                <div className="mt-3">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={onLoadMoreHiddenResolved}
                  >
                    Load more hidden (+5)
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

export default function IncidentBoardPage() {
  const { user, hasPermission } = useAuth();
  const [incidentDrafts, setIncidentDrafts] = useState({});
  const [expandedNotes, setExpandedNotes] = useState(new Set());
  const [incidentModalTab, setIncidentModalTab] = useState("details");
  const [incidentVisibilityTab, setIncidentVisibilityTab] = useLocalStorage(
    "incidents-visibility",
    "public",
  );
  const [selectedGroup, setSelectedGroup] = useLocalStorage(
    "incidents-selected-group",
    "",
  );
  const [groups, setGroups] = useState([]);
  const [incidentModal, setIncidentModal] = useState({
    isOpen: false,
    incident: null,
  });
  const [dropping, setDropping] = useState({});
  const [assigneeSearch, setAssigneeSearch] = useState("");
  const [showHiddenResolved, setShowHiddenResolved] = useState(false);
  const [hiddenResolvedVisibleCount, setHiddenResolvedVisibleCount] =
    useState(5);
  const [jiraCreating, setJiraCreating] = useState({});
  const [jiraProjects, setJiraProjects] = useState([]);
  const [jiraIntegrations, setJiraIntegrations] = useState([]);
  const [jiraIssueTypes, setJiraIssueTypes] = useState([]);
  const [jiraComments, setJiraComments] = useState([]);
  const [jiraCommentsLoading, setJiraCommentsLoading] = useState(false);
  const [incidentSummary, setIncidentSummary] = useState(null);
  const toast = useToast();

  const canReadUsers =
    hasPermission("read:users") || hasPermission("manage:users");
  const canUpdateIncidents = hasPermission("update:incidents");

  const {
    incidents,
    incidentUsers,
    loading,
    error,
    refresh,
    setIncidents,
    setError,
  } = useIncidentsData({
    visibilityTab: incidentVisibilityTab,
    selectedGroup,
    showHiddenResolved,
    canReadUsers,
  });

  const loadGroups = useCallback(async () => {
    try {
      const groupsData = await getGroups();
      const allGroups = Array.isArray(groupsData) ? groupsData : [];
      const userGroupIds = new Set(
        [
          ...(user?.group_ids || user?.groupIds || []).map((id) => String(id)),
          ...(Array.isArray(user?.groups) ? user.groups : []).map((group) =>
            String(group?.id || ""),
          ),
        ].filter(Boolean),
      );

      const memberGroups =
        userGroupIds.size > 0
          ? allGroups.filter((group) =>
              userGroupIds.has(String(group?.id || "")),
            )
          : allGroups;

      setGroups(memberGroups);

      if (
        selectedGroup &&
        !memberGroups.some(
          (group) => String(group?.id || "") === String(selectedGroup),
        )
      ) {
        setSelectedGroup("");
      }
    } catch (e) {
      console.error("Failed to load groups:", e);
    }
  }, [
    selectedGroup,
    setSelectedGroup,
    user?.group_ids,
    user?.groupIds,
    user?.groups,
  ]);

  useEffect(() => {
    loadGroups();
  }, [loadGroups]);

  useEffect(() => {
    loadJiraIntegrations();
  }, []);

  const loadIncidentSummary = useCallback(async () => {
    try {
      const summary = await getIncidentsSummary();
      setIncidentSummary(summary || null);
    } catch {
      setIncidentSummary(null);
    }
  }, []);

  useEffect(() => {
    loadIncidentSummary();
    const timer = setInterval(loadIncidentSummary, 30000);
    return () => clearInterval(timer);
  }, [loadIncidentSummary]);

  async function loadJiraIntegrations() {
    try {
      const data = await listJiraIntegrations();
      const items = Array.isArray(data?.items) ? data.items : [];
      setJiraIntegrations(items);
    } catch {
      setJiraIntegrations([]);
    }
  }

  const loadJiraIssueTypes = useCallback(async (projectKey, integrationId) => {
    try {
      if (!projectKey) {
        setJiraIssueTypes([]);
        return;
      }
      const data = await listJiraIssueTypes(projectKey, integrationId);
      setJiraIssueTypes(Array.isArray(data?.issueTypes) ? data.issueTypes : []);
    } catch {
      setJiraIssueTypes([]);
    }
  }, []);

  const loadJiraComments = useCallback(async (incidentId) => {
    if (!incidentId) return;
    setJiraCommentsLoading(true);
    try {
      const data = await listIncidentJiraComments(incidentId);
      setJiraComments(Array.isArray(data?.comments) ? data.comments : []);
    } catch {
      setJiraComments([]);
    } finally {
      setJiraCommentsLoading(false);
    }
  }, []);

  const incidentsByState = useMemo(() => {
    return {
      unresolved: incidents.filter(
        (incident) => incident.status !== "resolved",
      ),
      unassigned: incidents.filter(
        (incident) => incident.status !== "resolved" && !incident.assignee,
      ),
      assigned: incidents.filter(
        (incident) => incident.status !== "resolved" && !!incident.assignee,
      ),
      resolved: incidents.filter((incident) => incident.status === "resolved"),
    };
  }, [incidents]);

  const resolvedVisibleItems = useMemo(
    () =>
      incidentsByState.resolved.filter(
        (incident) => !incident.hideWhenResolved,
      ),
    [incidentsByState.resolved],
  );

  const hiddenResolvedItems = useMemo(
    () =>
      incidentsByState.resolved.filter((incident) => !!incident.hideWhenResolved),
    [incidentsByState.resolved],
  );

  useEffect(() => {
    setHiddenResolvedVisibleCount(5);
  }, [
    showHiddenResolved,
    incidentVisibilityTab,
    selectedGroup,
    hiddenResolvedItems.length,
  ]);

  const userById = useMemo(() => {
    const map = {};
    for (const userItem of incidentUsers) {
      map[userItem.id] = userItem;
    }
    return map;
  }, [incidentUsers]);

  const assignableIncidentUsers = useMemo(() => {
    const incident = incidentModal.incident;
    if (!incident) return [];

    const visibility = String(incident.visibility || "public").toLowerCase();
    if (visibility === "private") {
      return incidentUsers.filter(
        (userItem) =>
          String(userItem?.id || "") ===
          String(user?.id || user?.user_id || ""),
      );
    }

    if (visibility === "group") {
      const sharedGroupIds = new Set(
        (Array.isArray(incident.sharedGroupIds)
          ? incident.sharedGroupIds
          : []
        ).map((id) => String(id)),
      );
      if (sharedGroupIds.size === 0) return [];
      return incidentUsers.filter((userItem) => {
        const userGroupIds = new Set(
          [
            ...(Array.isArray(userItem?.group_ids)
              ? userItem.group_ids
              : []
            ).map((id) => String(id)),
            ...(Array.isArray(userItem?.groupIds) ? userItem.groupIds : []).map(
              (id) => String(id),
            ),
            ...(Array.isArray(userItem?.groups) ? userItem.groups : []).map(
              (group) => String(group?.id || ""),
            ),
          ].filter(Boolean),
        );
        for (const gid of userGroupIds) {
          if (sharedGroupIds.has(gid)) return true;
        }
        return false;
      });
    }

    return incidentUsers;
  }, [incidentModal.incident, incidentUsers, user]);

  const filteredIncidentUsers = useMemo(() => {
    const q = assigneeSearch.trim().toLowerCase();
    if (!q) return assignableIncidentUsers.slice(0, 20);
    return assignableIncidentUsers.filter((userItem) => {
      const haystack = [
        userItem.full_name,
        userItem.username,
        userItem.email,
        userItem.id,
      ];
      return haystack.some((h) => h?.toLowerCase().includes(q));
    });
  }, [assignableIncidentUsers, assigneeSearch]);

  const RESOLVE_BLOCK_TOAST = "Alert still active. Resolve it first.";

  const isResolveBlockedError = useCallback((err) => {
    const detail = String(err?.body?.detail || err?.message || "").toLowerCase();
    return (
      Number(err?.status) === 400 &&
      detail.includes("underlying alert is still active")
    );
  }, []);

  const ensureCanResolveIncident = useCallback(
    async (incident, { quietOnCheckError = false } = {}) => {
      if (!incident?.fingerprint) return true;
      try {
        const activeAlerts = await getAlertsByFilter(
          { fingerprint: incident.fingerprint },
          true,
        );
        if (Array.isArray(activeAlerts) && activeAlerts.length > 0) {
          try {
            toast.error(RESOLVE_BLOCK_TOAST);
          } catch (_) {}
          return false;
        }
      } catch (err) {
        if (!quietOnCheckError) {
          try {
            toast.error(
              err?.body?.detail ||
                err?.message ||
                "Failed to validate alert state before resolving",
            );
          } catch (_) {}
        }
      }
      return true;
    },
    [toast],
  );

  
  const formatDateTime = (iso) => {
    if (!iso) return "unknown time";
    try {
      const d = new Date(iso);
      const pad = (n) => String(n).padStart(2, "0");
      const day = pad(d.getDate());
      const month = pad(d.getMonth() + 1);
      const year = d.getFullYear();
      let hours = d.getHours();
      const ampm = hours >= 12 ? "pm" : "am";
      hours = hours % 12 || 12;
      const hh = pad(hours);
      const mm = pad(d.getMinutes());
      const ss = pad(d.getSeconds());
      return `${day}/${month}/${year}, ${hh}:${mm}:${ss} ${ampm}`;
    } catch (e) {
      return String(iso);
    }
  };

  const resolveAuthorLabel = useCallback(
    (author) => {
      const raw = String(author || "").trim();
      if (!raw) return "Unknown user";

      const userItem = userById[raw];
      if (userItem) return getUserLabel(userItem);

      const meId = String(user?.id || user?.user_id || "").trim();
      if (meId && raw === meId) {
        return getUserLabel(user || { id: meId, username: "me" });
      }

      const looksLikeId = /^[0-9a-f-]{20,}$/i.test(raw);
      return looksLikeId ? "Unknown user" : raw;
    },
    [userById, user],
  );

  const replaceUserIdsInText = useCallback(
    (text) => {
      let out = String(text || "");
      if (!out) return out;

      out = out.replace(
        /\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b/gi,
        (id, _group, offset, source) => {
          const before = String(source || "").charAt(Math.max(0, Number(offset) - 1));
          if (before === "#") return id;
          return resolveAuthorLabel(id);
        },
      );

      Object.entries(userById).forEach(([id, userItem]) => {
        const label = getUserLabel(userItem);
        const rx = new RegExp(`\\b${escapeRegExp(id)}\\b`, "g");
        out = out.replace(rx, (matched, offset, source) => {
          const before = String(source || "").charAt(Math.max(0, Number(offset) - 1));
          if (before === "#") return matched;
          return label;
        });
      });

      return out;
    },
    [userById, resolveAuthorLabel],
  );

  const openIncidentModal = useCallback((incident) => {
    const defaultIntegrationId =
      incident.jiraIntegrationId || jiraIntegrations[0]?.id || "";
    const draftDefaults = {
      assignee: incident.assignee ?? "",
      status: incident.status,
      note: "",
      jiraTicketKey: incident.jiraTicketKey ?? "",
      jiraTicketUrl: incident.jiraTicketUrl ?? "",
      jiraIntegrationId: defaultIntegrationId,
      hideWhenResolved: incident.hideWhenResolved ?? false,
      
      projectKey: incidentDrafts?.[incident.id]?.projectKey || "",
      issueType: incidentDrafts?.[incident.id]?.issueType || "Task",
    };

    setIncidentModal({ isOpen: true, incident });
    setAssigneeSearch("");
    setExpandedNotes(new Set());
    setIncidentModalTab("details");
    setIncidentDrafts((prev) => ({
      ...prev,
      [incident.id]: { ...(prev[incident.id] || {}), ...draftDefaults },
    }));

    if (defaultIntegrationId) {
      listJiraProjectsByIntegration(defaultIntegrationId)
        .then((data) => {
          const projects = Array.isArray(data?.projects) ? data.projects : [];
          setJiraProjects(projects);
          const requestedProject = (draftDefaults.projectKey || "").trim();
          const hasRequestedProject = projects.some(
            (project) => String(project?.key || "") === requestedProject,
          );
          const selectedProject = hasRequestedProject
            ? requestedProject
            : (projects[0]?.key || "");
          setIncidentDrafts((prev) => ({
            ...prev,
            [incident.id]: {
              ...(prev[incident.id] || {}),
              projectKey: selectedProject,
            },
          }));
          if (selectedProject) {
            loadJiraIssueTypes(selectedProject, defaultIntegrationId);
          } else {
            setJiraIssueTypes([]);
          }
        })
        .catch((err) => {
          setJiraProjects([]);
          setJiraIssueTypes([]);
          try {
            toast.error(
              err?.body?.detail ||
                err?.message ||
                "Failed to load Jira projects for integration",
            );
          } catch (_) {}
        });
    } else {
      setJiraProjects([]);
      setJiraIssueTypes([]);
    }

    loadJiraComments(incident.id);
  }, [
    incidentDrafts,
    jiraIntegrations,
    loadJiraComments,
    loadJiraIssueTypes,
    toast,
  ]);

  const IncidentModalTabs = ({ tab, setTab }) => (
    <div className="mt-4 inline-flex bg-sre-bg-alt rounded-lg p-1 border border-sre-border">
      <button
        type="button"
        onClick={() => setTab("details")}
        aria-pressed={tab === "details"}
        className={`px-4 py-2 text-sm rounded-md transition-all ${tab === "details" ? "bg-sre-primary/10 text-sre-primary" : "text-sre-text-muted hover:text-sre-text"}`}
      >
        <span className="material-icons text-sm mr-2">info</span>
        Details
      </button>

      <button
        type="button"
        onClick={() => setTab("assignment")}
        aria-pressed={tab === "assignment"}
        className={`px-4 py-2 text-sm rounded-md transition-all ${tab === "assignment" ? "bg-sre-primary/10 text-sre-primary" : "text-sre-text-muted hover:text-sre-text"}`}
      >
        <span className="material-icons text-sm mr-2">person</span>
        Assignment
      </button>

      <button
        type="button"
        onClick={() => setTab("jira")}
        aria-pressed={tab === "jira"}
        className={`px-4 py-2 text-sm rounded-md transition-all ${tab === "jira" ? "bg-sre-primary/10 text-sre-primary" : "text-sre-text-muted hover:text-sre-text"}`}
      >
        <span className="material-icons text-sm mr-2">link</span>
        Jira
      </button>

      <button
        type="button"
        onClick={() => setTab("notes")}
        aria-pressed={tab === "notes"}
        className={`px-4 py-2 text-sm rounded-md transition-all ${tab === "notes" ? "bg-sre-primary/10 text-sre-primary" : "text-sre-text-muted hover:text-sre-text"}`}
      >
        <span className="material-icons text-sm mr-2">notes</span>
        Notes
      </button>
    </div>
  );

  const IncidentBehavior = ({ incident, draft, setIncidentDrafts }) => {
    if (!incident) return null;
    return (
      <div className="mt-4">
        <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">
          <span className="material-icons font-bold  text-sm mr-1 align-middle">
            settings
          </span>
          Behavior
        </label>
        <div className="p-2 border border-sre-border rounded-xl p-3 bg-sre-bg-alt flex items-center justify-between gap-4 max-w-[400px]">
          <div className="text-sm text-sre-text flex items-center gap-3">
            <span className="material-icons text-sm mr-1">visibility_off</span>
            Hide when resolved
          </div>
          <div>
            <label className="inline-flex items-center gap-2  p-2 cursor-pointer">
              <input
                type="checkbox"
                checked={
                  draft.hideWhenResolved ?? incident.hideWhenResolved ?? false
                }
                onChange={(e) =>
                  setIncidentDrafts((prev) => ({
                    ...prev,
                    [incident.id]: {
                      ...(prev[incident.id] || {}),
                      hideWhenResolved: e.target.checked,
                    },
                  }))
                }
                className="form-checkbox h-4 w-4 text-sre-primary"
              />
            </label>
          </div>
        </div>
      </div>
    );
  };

  const handleDropOnColumn = useCallback(
    async (target, e) => {
      e.preventDefault();
      let droppedId;
      try {
        const id = e.dataTransfer.getData("text/incident");
        if (!id) return;
        droppedId = id;
        setDropping((prev) => ({ ...prev, [droppedId]: true }));
        const incident = incidents.find(
          (it) => String(it.id) === String(droppedId),
        );
        if (!incident) {
          setDropping((prev) => clearDroppedState(prev, droppedId));
          return;
        }

        const payload = {};
        if (target === "unassigned") {
          payload.assignee = null;
          payload.status = "open";
        } else if (target === "assigned") {
          if (!incident.assignee) {
            setDropping((prev) => clearDroppedState(prev, droppedId));
            openIncidentModal(incident);
            setIncidentModalTab("assignment");
            try {
              toast.info("Choose an assignee to move this incident to Assigned");
            } catch (_) {}
            return;
          }
          payload.status = "open";
        } else if (target === "resolved") {
          payload.status = "resolved";
        }

        if (target === "resolved") {
          const canResolve = await ensureCanResolveIncident(incident, {
            quietOnCheckError: true,
          });
          if (!canResolve) {
            setDropping((prev) => clearDroppedState(prev, droppedId));
            return;
          }
        }

        await updateIncident(id, payload);
        setDropping((prev) => clearDroppedState(prev, droppedId));
        await refresh();
      } catch (err) {
        const detail =
          isResolveBlockedError(err)
            ? RESOLVE_BLOCK_TOAST
            : err?.body?.detail || err?.message || "Unable to update incident";
        setError(detail);
        try {
          toast.error(detail);
        } catch (_) {}
      } finally {
        setDropping((prev) => clearDroppedState(prev, droppedId));
      }
    },
    [
      ensureCanResolveIncident,
      incidents,
      isResolveBlockedError,
      openIncidentModal,
      refresh,
      setError,
      setIncidentModalTab,
      toast,
    ],
  );

  const handleQuickResolveIncident = useCallback(
    async (incident) => {
      if (!incident?.id) return;
      const droppedId = String(incident.id);
      try {
        setDropping((prev) => ({ ...prev, [droppedId]: true }));
        const canResolve = await ensureCanResolveIncident(incident, {
          quietOnCheckError: true,
        });
        if (!canResolve) {
          return;
        }
        await updateIncident(incident.id, { status: "resolved" });
        await refresh();
      } catch (err) {
        const detail =
          isResolveBlockedError(err)
            ? RESOLVE_BLOCK_TOAST
            : err?.body?.detail || err?.message || "Unable to update incident";
        setError(detail);
        try {
          toast.error(detail);
        } catch (_) {}
      } finally {
        setDropping((prev) => clearDroppedState(prev, droppedId));
      }
    },
    [ensureCanResolveIncident, isResolveBlockedError, refresh, setError, toast],
  );

  const handleSaveIncident = useCallback(
    async (incident) => {
      const draft = incidentDrafts[incident.id] || {};
      const payload = {
        assignee: draft.assignee || null,
        status: draft.status || incident.status,
        note: draft.note || null,
        jiraTicketKey: draft.jiraTicketKey || null,
        jiraTicketUrl: draft.jiraTicketUrl || null,
        jiraIntegrationId:
          draft.jiraIntegrationId || incident.jiraIntegrationId || null,
        hideWhenResolved:
          typeof draft.hideWhenResolved !== "undefined"
            ? draft.hideWhenResolved
            : incident.hideWhenResolved || false,
      };

      if (payload.status === "resolved") {
        const canResolve = await ensureCanResolveIncident(incident, {
          quietOnCheckError: true,
        });
        if (!canResolve) {
          return;
        }
      }

      try {
        await updateIncident(incident.id, payload);
        setIncidentModal({ isOpen: false, incident: null });
        setAssigneeSearch("");
        setIncidentDrafts((prev) => {
          const next = { ...prev };
          delete next[incident.id];
          return next;
        });
        await refresh();
      } catch (err) {
        const detail =
          isResolveBlockedError(err)
            ? RESOLVE_BLOCK_TOAST
            : err?.body?.detail || err?.message || "Unable to update incident";
        setError(detail);
        try {
          toast.error(detail);
        } catch (_) {}
      }
    },
    [
      ensureCanResolveIncident,
      incidentDrafts,
      isResolveBlockedError,
      refresh,
      setError,
      toast,
    ],
  );

  useEffect(() => {
    if (!incidentModal.isOpen) return;
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        const current = incidentModal.incident;
        if (canUpdateIncidents && current) handleSaveIncident(current);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [
    incidentModal.isOpen,
    incidentModal.incident,
    canUpdateIncidents,
    handleSaveIncident,
  ]);

  const handleAddNote = useCallback(
    async (incidentId) => {
      const draft = incidentDrafts[incidentId] || {};
      const text = (draft.note || "").trim();
      if (!text) return;

      try {
        const updated = await updateIncident(incidentId, { note: text });

        
        setIncidentModal(() => ({ isOpen: true, incident: updated }));

        
        setIncidentDrafts((prev) => ({
          ...prev,
          [incidentId]: { ...(prev[incidentId] || {}), note: "" },
        }));

        
        setIncidents((prev) =>
          prev.map((it) =>
            String(it.id) === String(updated.id) ? updated : it,
          ),
        );

        await loadJiraComments(incidentId);
        try {
          toast.success("Note added");
        } catch (_) {}
      } catch (e) {
        try {
          toast.error(e?.body?.detail || e?.message || "Failed to add note");
        } catch (_) {}
      }
    },
    [incidentDrafts, setIncidentDrafts, setIncidents, loadJiraComments, toast],
  );

  const handleUnhideIncident = useCallback(
    async (incidentId) => {
      try {
        setDropping((prev) => ({ ...prev, [incidentId]: true }));
        await updateIncident(incidentId, { hideWhenResolved: false });
        await refresh();
        try {
          toast.success("Incident unhidden");
        } catch (_) {}
      } catch (err) {
        setError(
          err?.body?.detail || err?.message || "Unable to unhide incident",
        );
        try {
          toast.error(
            err?.body?.detail || err?.message || "Unable to unhide incident",
          );
        } catch (_) {}
      } finally {
        setDropping((prev) => {
          const next = { ...prev };
          delete next[incidentId];
          return next;
        });
      }
    },
    [refresh, setError, toast],
  );

  const handleHideIncident = useCallback(
    async (incidentId) => {
      try {
        setDropping((prev) => ({ ...prev, [incidentId]: true }));
        await updateIncident(incidentId, { hideWhenResolved: true });
        await refresh();
        try {
          toast.success("Incident hidden");
        } catch (_) {}
      } catch (err) {
        setError(
          err?.body?.detail || err?.message || "Unable to hide incident",
        );
        try {
          toast.error(
            err?.body?.detail || err?.message || "Unable to hide incident",
          );
        } catch (_) {}
      } finally {
        setDropping((prev) => {
          const next = { ...prev };
          delete next[incidentId];
          return next;
        });
      }
    },
    [refresh, setError, toast],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-16">
        <Alert variant="error" className="max-w-md mx-auto">
          {error}
        </Alert>
      </div>
    );
  }

  const activeIncident = incidentModal.incident;
  const activeIncidentDraft = activeIncident
    ? incidentDrafts[activeIncident.id] || {}
    : {};
  const isIncidentLinkedToJira = Boolean(
    activeIncident?.jiraTicketKey || activeIncidentDraft?.jiraTicketKey,
  );
  const jiraIssueTypeOptions = (() => {
    const filtered = (Array.isArray(jiraIssueTypes) ? jiraIssueTypes : []).filter(
      (issueType) => {
        const normalized = String(issueType || "").trim().toLowerCase();
        return normalized === "task" || normalized === "bug";
      },
    );
    if (filtered.length > 0) return filtered;
    return ["Task", "Bug"];
  })();
  const activeIncidentAssigneeLabel = activeIncident
    ? getIncidentAssigneeLabel(activeIncident, userById, user)
    : "Unassigned";
  const stats = {
    totalIncidents: incidents.length,
    unresolved: incidentsByState.unresolved.length,
    unassigned: incidentsByState.unassigned.length,
    assignedToMe:
      incidentSummary?.assigned_to_me_open ??
      incidentsByState.assigned.filter(
        (incident) =>
          String(incident.assignee || "") ===
          String(user?.id || user?.user_id || ""),
      ).length,
  };

  return (
    <div className="min-h-screen via-sre-bg-alt to-sre-bg">
      <div className="">
        <div className="mb-8">
          <div className="flex items-center justify-between ">
            <div className="flex flex-col gap-4">
              <div>
                <h1 className="text-3xl font-bold text-sre-text">
                  <span className="material-icons text-3xl text-sre-primary">
                    assignment
                  </span>{" "}
                  InOps
                </h1>
                <p className="text-sre-text-muted mt-1">
                  Manage and track incident response workflows
                </p>
              </div>

              <div className="mb-5">
                <div className="flex mt-0 items-center gap-2 p-1 bg-sre-surface rounded-lg border border-sre-border w-fit">
                  <Button
                    variant={
                      incidentVisibilityTab === "public" ? "primary" : "ghost"
                    }
                    size="sm"
                    onClick={() => {
                      setIncidentVisibilityTab("public");
                      setSelectedGroup("");
                    }}
                    className="relative px-5 py-2 pr-8"
                  >
                    <span className="material-icons text-sm mr-2">public</span>
                    Public
                    <span className="absolute -top-2 -right-2 inline-flex h-6 min-w-6 items-center justify-center rounded-full border border-sre-border bg-sre-surface text-blue-400 text-[10px] font-semibold px-1 shadow-sm">
                      {incidentSummary?.by_visibility?.public ?? 0}
                    </span>
                  </Button>
                  <Button
                    variant={
                      incidentVisibilityTab === "private" ? "primary" : "ghost"
                    }
                    size="sm"
                    onClick={() => {
                      setIncidentVisibilityTab("private");
                      setSelectedGroup("");
                    }}
                    className="relative px-5 py-2 pr-8"
                  >
                    <span className="material-icons text-sm mr-2">lock</span>
                    Private
                    <span className="absolute -top-2 -right-2 inline-flex h-6 min-w-6 items-center justify-center rounded-full border border-sre-border bg-sre-surface text-amber-400 text-[10px] font-semibold px-1 shadow-sm">
                      {incidentSummary?.by_visibility?.private ?? 0}
                    </span>
                  </Button>
                  <Button
                    variant={
                      incidentVisibilityTab === "group" ? "primary" : "ghost"
                    }
                    size="sm"
                    onClick={() => setIncidentVisibilityTab("group")}
                    className="relative px-5 py-2 pr-8"
                  >
                    <span className="material-icons text-sm mr-2">group</span>
                    Group
                    <span className="absolute -top-2 -right-2 inline-flex h-6 min-w-6 items-center justify-center rounded-full border border-sre-border bg-sre-surface text-emerald-400 text-[10px] font-semibold px-1 shadow-sm">
                      {incidentSummary?.by_visibility?.group ?? 0}
                    </span>
                  </Button>
                </div>
                <div className="mt-2 w-fit">
                  {incidentVisibilityTab === "group" &&
                    (groups.length > 0 ? (
                      <Select
                        value={selectedGroup}
                        onChange={(valueOrEvent) =>
                          setSelectedGroup(
                            valueOrEvent?.target?.value ?? valueOrEvent ?? "",
                          )
                        }
                        placeholder="Select group..."
                      >
                        {groups.map((group) => (
                          <option key={group.id} value={group.id}>
                            {group.name}
                          </option>
                        ))}
                      </Select>
                    ) : (
                      <div className="truncate text-sre-text-muted text-sm px-3 py-2 bg-sre-surface border border-sre-border rounded">
                        No groups available to you ...
                      </div>
                    ))}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-6">
              {/* Stats */}
              <div className="flex items-center gap-4 text-sm">
                <div className="flex items-center gap-2 px-3 py-2 bg-sre-surface rounded-lg border border-sre-border">
                  <span className="material-icons text-base text-orange-500">
                    warning
                  </span>
                  <span className="font-medium text-sre-text">
                    {stats.unresolved}
                  </span>
                  <span className="text-sre-text-muted">unresolved</span>
                  <HelpTooltip text="Number of incidents that are still open and require attention." />
                </div>
                <div className="flex items-center gap-2 px-3 py-2 bg-sre-surface rounded-lg border border-sre-border">
                  <span className="material-icons text-base text-blue-500">
                    person_off
                  </span>
                  <span className="font-medium text-sre-text">
                    {stats.unassigned}
                  </span>
                  <span className="text-sre-text-muted">unassigned</span>
                  <HelpTooltip text="Number of open incidents that haven't been assigned to anyone yet." />
                </div>
                <div className="flex items-center gap-2 px-3 py-2 bg-sre-surface rounded-lg border border-sre-border">
                  <span className="material-icons text-base text-gray-500">
                    assignment_turned_in
                  </span>
                  <span className="font-medium text-sre-text">
                    {stats.totalIncidents}
                  </span>
                  <span className="text-sre-text-muted">total</span>
                  <HelpTooltip text="Total number of incidents currently visible based on your filters." />
                </div>
                <div className="flex items-center gap-2 px-3 py-2 bg-sre-surface rounded-lg border border-sre-border">
                  <span className="material-icons text-base text-green-500">
                    person
                  </span>
                  <span className="font-medium text-sre-text">
                    {stats.assignedToMe}
                  </span>
                  <HelpTooltip text="Open incidents currently assigned to you." />
                </div>
              </div>

              <div className="flex items-center gap-2">
                <label className="inline-flex items-center gap-2 text-sm text-sre-text-muted">
                  <input
                    type="checkbox"
                    className="form-checkbox h-4 w-4"
                    checked={showHiddenResolved}
                    onChange={(e) => {
                      setShowHiddenResolved(e.target.checked);
                    }}
                  />
                  <span>Show hidden</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        {/* Board */}
        {incidents.length > 0 ? (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 min-h-[600px]">
            <>
              <Column
                title="To Do"
                count={incidentsByState.unassigned.length}
                colorDot="bg-blue-500"
                icon="unassigned"
                help="New or re-opened incidents awaiting assignment."
                items={incidentsByState.unassigned}
                empty={{
                  icon: "person_off",
                  title: "No incidents in To Do",
                  subtitle: "New and re-opened incidents appear here",
                }}
                canUpdateIncidents={canUpdateIncidents}
                onDropColumn={handleDropOnColumn}
                userById={userById}
                currentUser={user}
                openIncidentModal={openIncidentModal}
                setIncidentModalTab={setIncidentModalTab}
                onQuickResolve={handleQuickResolveIncident}
                handleUnhideIncident={handleUnhideIncident}
                handleHideIncident={handleHideIncident}
                dropping={dropping}
              />

              <Column
                title="Assigned Active"
                count={incidentsByState.assigned.length}
                colorDot="bg-green-500"
                icon="assigned"
                help="Incidents that have been assigned to someone and are currently being worked on."
                items={incidentsByState.assigned}
                empty={{
                  icon: "engineering",
                  title: "No active incidents",
                  subtitle: "Assigned incidents in progress",
                }}
                canUpdateIncidents={canUpdateIncidents}
                onDropColumn={handleDropOnColumn}
                userById={userById}
                currentUser={user}
                openIncidentModal={openIncidentModal}
                setIncidentModalTab={setIncidentModalTab}
                onQuickResolve={handleQuickResolveIncident}
                handleUnhideIncident={handleUnhideIncident}
                handleHideIncident={handleHideIncident}
                dropping={dropping}
              />

              <Column
                title="Resolved"
                count={incidentsByState.resolved.length}
                colorDot="bg-purple-500"
                icon="resolved"
                help="Incidents that have been resolved and closed. These may be hidden by default."
                items={resolvedVisibleItems}
                empty={{
                  icon: "check_circle",
                  title: "No resolved incidents",
                  subtitle: "Completed incident responses",
                }}
                canUpdateIncidents={canUpdateIncidents}
                onDropColumn={handleDropOnColumn}
                userById={userById}
                currentUser={user}
                openIncidentModal={openIncidentModal}
                setIncidentModalTab={setIncidentModalTab}
                onQuickResolve={handleQuickResolveIncident}
                handleUnhideIncident={handleUnhideIncident}
                handleHideIncident={handleHideIncident}
                dropping={dropping}
                hiddenResolvedItems={hiddenResolvedItems}
                hiddenResolvedVisibleCount={hiddenResolvedVisibleCount}
                onLoadMoreHiddenResolved={() =>
                  setHiddenResolvedVisibleCount((prev) => prev + 5)
                }
              />
            </>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-20 px-6">
            <div className="p-6  mb-6">
              <span className="material-icons text-6xl text-sre-text-muted/50">
                assignment_turned_in
              </span>
            </div>
            <h3 className="text-xl font-semibold text-sre-text mb-2">
              No incidents found
            </h3>
            <p className="text-sre-text-muted text-sm text-center max-w-md">
              Ensure you have the permissions to view incidents and that your
              filters are set correctly. Try adjusting the visibility or group
              filters, or check back later when new incidents are created.
            </p>
          </div>
        )}

        {activeIncident && (
          <Modal
            isOpen={incidentModal.isOpen}
            onClose={() => {
              setIncidentModal({ isOpen: false, incident: null });
              setAssigneeSearch("");
            }}
            title={`Updating Incident #${activeIncident.id}`}
            size="lg"
            closeOnOverlayClick={false}
          >
            <div className="space-y-6">
              <div className="mb-4">
                <div className="flex items-center justify-between gap-4 pb-3 border-b border-sre-border/60">
                  <div className="min-w-0">
                    <h3 className="text-2xl font-bold text-sre-text truncate">
                      {activeIncident.alertName}
                    </h3>
                    <p className="text-xs text-sre-text-muted mt-1 truncate">
                      {activeIncident.fingerprint
                        ? `Fingerprint: ${activeIncident.fingerprint}`
                        : activeIncident.alertName}
                    </p>
                  </div>

                  <div className="flex items-center gap-3">
                    <Badge
                      variant={
                        activeIncident.severity === "critical"
                          ? "error"
                          : activeIncident.severity === "warning"
                            ? "warning"
                            : "info"
                      }
                      className="text-xs px-2 py-0.5 rounded-full font-semibold"
                    >
                      <span className="uppercase">
                        {activeIncident.severity}
                      </span>
                    </Badge>

                    <div
                      className={`px-2 py-0.5 rounded-full border border-sre-border text-xs ${activeIncident.status === "resolved" ? "bg-sre-success/5 text-sre-success" : "bg-sre-warning/5 text-sre-warning"}`}
                    >
                      {activeIncident.status}
                    </div>

                    <div className="flex items-center gap-2 px-2 py-0.5 rounded-full bg-sre-bg-alt border border-sre-border">
                      <div className="w-5 h-5 rounded-full bg-gradient-to-br from-sre-primary/10 to-sre-primary/5 text-sre-primary flex items-center justify-center text-[10px] font-semibold border border-sre-border/40 flex-shrink-0">
                        {String(
                          activeIncidentAssigneeLabel || "U" || "",
                        )
                          .split(" ")
                          .map((s) => s[0])
                          .slice(0, 2)
                          .join("")
                          .toUpperCase()}
                      </div>
                      <div className="text-xs text-sre-text truncate">
                        {activeIncidentAssigneeLabel}
                      </div>
                    </div>

                    <div className="text-xs text-sre-text-muted ml-2 hidden sm:block">
                      {new Date(activeIncident.lastSeenAt).toLocaleString()}
                    </div>
                  </div>
                </div>

                <IncidentModalTabs
                  tab={incidentModalTab}
                  setTab={setIncidentModalTab}
                />
                <IncidentBehavior
                  incident={activeIncident}
                  draft={activeIncidentDraft}
                  setIncidentDrafts={setIncidentDrafts}
                />
              </div>

              {incidentModalTab === "details" && (
                <Card>
                  <h4 className="text-sm font-semibold text-sre-text text-left mb-3 flex items-center">
                    <span className="material-icons text-base mr-2">info</span>
                    Incident Details
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {(() => {
                      const correlationId = getIncidentCorrelationId(activeIncident);
                      const labelEntries = getIncidentLabelEntries(activeIncident);
                      return (
                        <>
                          <div>
                            <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">
                              Correlation ID
                            </label>
                            <div className="p-2 border border-sre-border rounded bg-sre-bg-alt text-sm text-sre-text break-all">
                              {correlationId || "N/A"}
                            </div>
                          </div>
                          <div className="md:col-span-2">
                            <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">
                              Labels
                            </label>
                            <div>
                              {labelEntries.length > 0 ? (
                                <div className="flex flex-wrap gap-2">
                                  {labelEntries.map(([key, value]) => (
                                    <Badge
                                      key={`${activeIncident.id}-details-label-${key}`}
                                      variant="ghost"
                                    >
                                      {key}: {String(value)}
                                    </Badge>
                                  ))}
                                </div>
                              ) : (
                                <div className="text-sm text-sre-text-muted">No labels</div>
                              )}
                            </div>
                          </div>
                        </>
                      );
                    })()}

                    <div>
                      <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">
                        Status
                      </label>
                      <div className="inline-flex rounded-lg bg-sre-bg-alt p-1 border border-sre-border">
                        <button
                          type="button"
                          className={`px-3 py-1.5 text-sm rounded-md transition ${(activeIncidentDraft.status ?? activeIncident.status) === "open" ? "bg-sre-primary text-white" : "text-sre-text-muted hover:text-sre-text"}`}
                          aria-pressed={
                            (activeIncidentDraft.status ??
                              activeIncident.status) === "open"
                          }
                          onClick={() =>
                            setIncidentDrafts((prev) => ({
                              ...prev,
                              [activeIncident.id]: {
                                ...(prev[activeIncident.id] || {}),
                                status: "open",
                              },
                            }))
                          }
                        >
                          Open
                        </button>
                        <button
                          type="button"
                          className={`ml-1 px-3 py-1.5 text-sm rounded-md transition ${(activeIncidentDraft.status ?? activeIncident.status) === "resolved" ? "bg-sre-success text-white" : "text-sre-text-muted hover:text-sre-text"}`}
                          aria-pressed={
                            (activeIncidentDraft.status ??
                              activeIncident.status) === "resolved"
                          }
                          onClick={async () => {
                            const canResolve = await ensureCanResolveIncident(
                              activeIncident,
                              { quietOnCheckError: true },
                            );
                            if (!canResolve) return;
                            setIncidentDrafts((prev) => ({
                              ...prev,
                              [activeIncident.id]: {
                                ...(prev[activeIncident.id] || {}),
                                status: "resolved",
                              },
                            }));
                          }}
                        >
                          Resolved
                        </button>
                      </div>
                      <p className="mt-1 text-xs text-sre-text-muted">
                        Quick toggle — resolving runs a safety check.
                      </p>
                    </div>

                    {/* Behavior moved under tabs */}
                  </div>
                </Card>
              )}

              {incidentModalTab === "assignment" && (
                <Card>
                  <h4 className="text-sm font-semibold text-sre-text text-left mb-3 flex items-center">
                    <span className="material-icons text-base mr-2">
                      person
                    </span>
                    Assignment
                  </h4>
                  {canReadUsers ? (
                    <div className="space-y-3">
                      <div className="flex gap-2 items-center">
                        <Input
                          className="flex-1"
                          value={assigneeSearch}
                          onChange={(e) => setAssigneeSearch(e.target.value)}
                          placeholder="Search users by name, username, or email"
                        />
                        <Button
                          size="xs"
                          variant="ghost"
                          onClick={() =>
                            setIncidentDrafts((prev) => ({
                              ...prev,
                              [activeIncident.id]: {
                                ...(prev[activeIncident.id] || {}),
                                assignee: user?.id || "",
                              },
                            }))
                          }
                          disabled={!canUpdateIncidents || !user?.id}
                          title="Assign to me"
                          className="flex items-center font-bold gap-1 whitespace-nowrap"
                        >
                          Assign to me
                        </Button>
                      </div>
                      <div className="max-h-36 overflow-auto border border-sre-border rounded-lg bg-sre-bg-alt">
                        <button
                          type="button"
                          className={`w-full text-left flex items-center gap-2 min-w-0 px-3 py-2 text-sm hover:bg-sre-surface transition-colors ${
                            !(
                              activeIncidentDraft.assignee ??
                              activeIncident.assignee
                            )
                              ? "text-sre-primary bg-sre-surface"
                              : "text-sre-text"
                          }`}
                          onClick={() =>
                            setIncidentDrafts((prev) => ({
                              ...prev,
                              [activeIncident.id]: {
                                ...(prev[activeIncident.id] || {}),
                                assignee: "",
                              },
                            }))
                          }
                        >
                          <span className="material-icons text-sm flex-shrink-0">
                            person_off
                          </span>
                          <span className="truncate min-w-0">Unassigned</span>
                        </button>
                        {filteredIncidentUsers.map((userItem) => {
                          const selected =
                            (activeIncidentDraft.assignee ??
                              activeIncident.assignee) === userItem.id;
                          return (
                            <button
                              type="button"
                              key={userItem.id}
                              className={`w-full text-left flex items-center gap-2 min-w-0 px-3 py-2 text-sm hover:bg-sre-surface transition-colors ${selected ? "text-sre-primary bg-sre-surface" : "text-sre-text"}`}
                              onClick={() =>
                                setIncidentDrafts((prev) => ({
                                  ...prev,
                                  [activeIncident.id]: {
                                    ...(prev[activeIncident.id] || {}),
                                    assignee: userItem.id,
                                  },
                                }))
                              }
                            >
                              <span className="material-icons text-sm flex-shrink-0">
                                person
                              </span>
                              <span className="truncate min-w-0">
                                {getUserLabel(userItem)}
                              </span>
                            </button>
                          );
                        })}
                        {filteredIncidentUsers.length === 0 && (
                          <div className="px-3 py-2 text-xs text-sre-text-muted">
                            No users found
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="text-sm text-sre-text-muted text-left p-3 bg-sre-bg-alt border border-sre-border rounded-lg">
                      You do not have permission to list users. Assignee changes
                      require read users access.
                    </div>
                  )}
                </Card>
              )}

              {incidentModalTab === "jira" && (
                <Card>
                  <h4 className="text-sm font-semibold text-sre-text text-left mb-3 flex items-center">
                    <span className="material-icons text-base mr-2">link</span>
                    Jira Integration
                  </h4>
                  <div className="grid grid-cols-1  md:grid-cols-2 gap-4">
                    <Input
                      value={activeIncidentDraft.jiraSummary ?? ""}
                      onChange={(e) =>
                        setIncidentDrafts((prev) => ({
                          ...prev,
                          [activeIncident.id]: {
                            ...(prev[activeIncident.id] || {}),
                            jiraSummary: e.target.value,
                          },
                        }))
                      }
                      className="min-w-[650px]"
                      placeholder="Optional: override ticket summary (defaults to incident title)"
                    />

                    {activeIncident.jiraTicketKey && (
                      <div className="flex items-center gap-3 ml-2">
                        <a
                          href={activeIncident.jiraTicketUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sre-primary font-medium"
                        >
                          {activeIncident.jiraTicketKey}
                        </a>
                        <span className="text-xs text-sre-text-muted">
                          Linked ticket
                        </span>
                      </div>
                    )}
                  </div>
                  {isIncidentLinkedToJira && (
                    <div className="mt-3 text-xs text-sre-text-muted text-left">
                      This incident is already linked to Jira. You can create a
                      new ticket to replace the existing link.
                    </div>
                  )}

                  {jiraIntegrations.length > 0 ? (
                    <div className="mt-3 grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
                      <div>
                        <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">
                          Jira integration
                        </label>
                        <Select
                          value={
                            activeIncidentDraft.jiraIntegrationId ??
                            (jiraIntegrations[0]?.id || "")
                          }
                          onChange={async (e) => {
                            const nextIntegrationId = e.target.value;
                            setIncidentDrafts((prev) => ({
                              ...prev,
                              [activeIncident.id]: {
                                ...(prev[activeIncident.id] || {}),
                                jiraIntegrationId: nextIntegrationId,
                                projectKey: "",
                              },
                            }));
                            try {
                              const projectData =
                                await listJiraProjectsByIntegration(
                                  nextIntegrationId,
                                );
                              const projects = Array.isArray(
                                projectData?.projects,
                              )
                                ? projectData.projects
                                : [];
                              setJiraProjects(projects);
                              const firstProject = projects[0]?.key || "";
                              if (firstProject) {
                                setIncidentDrafts((prev) => ({
                                  ...prev,
                                  [activeIncident.id]: {
                                    ...(prev[activeIncident.id] || {}),
                                    jiraIntegrationId: nextIntegrationId,
                                    projectKey: firstProject,
                                  },
                                }));
                                await loadJiraIssueTypes(
                                  firstProject,
                                  nextIntegrationId,
                                );
                              } else {
                                setJiraIssueTypes([]);
                              }
                            } catch (err) {
                              setJiraProjects([]);
                              setJiraIssueTypes([]);
                              try {
                                toast.error(
                                  err?.body?.detail ||
                                    err?.message ||
                                    "Failed to load Jira projects for integration",
                                );
                              } catch (_) {}
                            }
                          }}
                        >
                          {jiraIntegrations.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.name}
                            </option>
                          ))}
                        </Select>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">
                          Jira project
                        </label>
                        <Select
                          value={
                            activeIncidentDraft.projectKey ??
                            (jiraProjects[0]?.key || "")
                          }
                          onChange={(e) => {
                            const nextProject = e.target.value;
                            setIncidentDrafts((prev) => ({
                              ...prev,
                              [activeIncident.id]: {
                                ...(prev[activeIncident.id] || {}),
                                projectKey: nextProject,
                              },
                            }));
                            loadJiraIssueTypes(
                              nextProject,
                              activeIncidentDraft.jiraIntegrationId,
                            );
                          }}
                        >
                          {jiraProjects.length > 0 ? (
                            jiraProjects.map((project) => (
                              <option key={project.key} value={project.key}>
                                {project.key} — {project.name}
                              </option>
                            ))
                          ) : (
                            <option value="">No projects</option>
                          )}
                        </Select>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">
                          Issue type
                        </label>
                        <Select
                          value={activeIncidentDraft.issueType ?? "Task"}
                          onChange={(e) =>
                            setIncidentDrafts((prev) => ({
                              ...prev,
                              [activeIncident.id]: {
                                ...(prev[activeIncident.id] || {}),
                                issueType: e.target.value,
                              },
                            }))
                          }
                        >
                          {jiraIssueTypeOptions.map((issueType) => (
                            <option key={issueType} value={issueType}>
                              {issueType}
                            </option>
                          ))}
                        </Select>
                      </div>
                      <div className="md:col-span-2 flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="primary"
                          disabled={
                            !!jiraCreating[activeIncident.id] ||
                            !(
                              activeIncidentDraft.jiraIntegrationId ||
                              jiraIntegrations[0]?.id
                            )
                          }
                          onClick={async () => {
                            
                            if (!canUpdateIncidents) {
                              try {
                                toast.error(
                                  "Missing update:incidents permission",
                                );
                              } catch (_) {}
                              return;
                            }
                            const draft =
                              incidentDrafts[activeIncident.id] || {};
                            const integrationId = (
                              draft.jiraIntegrationId ||
                              jiraIntegrations[0]?.id ||
                              ""
                            ).trim();
                            const projectKey = (
                              draft.projectKey ||
                              jiraProjects[0]?.key ||
                              ""
                            ).trim();
                            const issueType = (
                              draft.issueType || "Task"
                            ).trim();
                            const normalizedIssueType =
                              String(issueType).toLowerCase() === "bug"
                                ? "Bug"
                                : "Task";
                            const summary =
                              (draft.jiraSummary && draft.jiraSummary.trim()) ||
                              activeIncident.alertName;
                            if (!integrationId) {
                              try {
                                toast.error("Choose a Jira integration first");
                              } catch (_) {}
                              return;
                            }
                            if (!projectKey) {
                              try {
                                toast.error("Choose a Jira project first");
                              } catch (_) {}
                              return;
                            }
                            try {
                              setJiraCreating((s) => ({
                                ...s,
                                [activeIncident.id]: true,
                              }));
                              const updated = await createIncidentJira(
                                activeIncident.id,
                                {
                                  integrationId,
                                  projectKey,
                                  issueType: normalizedIssueType,
                                  summary,
                                  replaceExisting: isIncidentLinkedToJira,
                                },
                              );
                              
                              setIncidentDrafts((prev) => ({
                                ...prev,
                                [activeIncident.id]: {
                                  ...(prev[activeIncident.id] || {}),
                                  jiraTicketKey: updated.jiraTicketKey || "",
                                  jiraTicketUrl: updated.jiraTicketUrl || "",
                                  jiraIntegrationId: integrationId,
                                },
                              }));
                              try {
                                toast.success(
                                  `Jira created: ${updated.jiraTicketKey}`,
                                );
                              } catch (_) {}
                              await loadJiraComments(activeIncident.id);
                              await refresh();
                            } catch (err) {
                              try {
                                toast.error(
                                  err?.body?.detail ||
                                    err?.message ||
                                    "Failed to create Jira ticket",
                                );
                              } catch (_) {}
                            } finally {
                              setJiraCreating((s) => ({
                                ...s,
                                [activeIncident.id]: false,
                              }));
                            }
                          }}
                        >
                          {jiraCreating[activeIncident.id] ? (
                            <>
                              <Spinner size="xs" />
                              <span className="ml-2">Creating…</span>
                            </>
                          ) : (
                            <span className="flex items-center gap-1">
                              <span className="material-icons text-sm">
                                {isIncidentLinkedToJira ? "autorenew" : "add"}
                              </span>
                              <span className="sr-only">
                                {isIncidentLinkedToJira ? "Create New Jira" : "Create Jira"}
                              </span>
                            </span>
                          )}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-3 text-xs text-sre-text-muted text-left">
                      <div className="text-left">
                        No accessible Jira integration found.{" "}
                        <a
                          href="/integrations"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sre-primary hover:underline"
                        >
                          Create Jira integration
                        </a>
                      </div>
                    </div>
                  )}

                  {activeIncident.jiraTicketKey && (
                    <div className="mt-3 p-3 border border-sre-border rounded-lg bg-sre-bg-alt space-y-2">
                      <div className="flex items-center gap-2">
                        <p className="text-xs font-medium text-sre-text text-left">
                          Jira comments
                        </p>
                      </div>

                      {jiraCommentsLoading ? (
                        <div className="text-xs text-sre-text-muted">
                          Loading Jira comments...
                        </div>
                      ) : (
                        <div className="space-y-2 max-h-40 overflow-auto">
                          {jiraComments.length === 0 ? (
                            <div className="text-xs text-sre-text-muted">
                              No Jira comments yet.
                            </div>
                          ) : (
                            jiraComments.map((comment) => (
                              <div
                                key={
                                  comment.id ||
                                  `${comment.author}-${comment.created}`
                                }
                                className="text-xs text-sre-text-muted text-left"
                              >
                                <span className="font-medium text-sre-text">
                                  {comment.author}
                                </span>{" "}
                                ·{" "}
                                {comment.created
                                  ? formatDateTime(comment.created)
                                  : "unknown time"}
                                <br />
                                {comment.body}
                              </div>
                            ))
                          )}
                        </div>
                      )}

                      <div className="text-xs text-sre-text-muted">
                        Jira comments are read-only here. Add notes in the
                        Notes tab to sync them to Jira automatically.
                      </div>
                    </div>
                  )}
                </Card>
              )}

              {incidentModalTab === "notes" && (
                <Card>
                  <h4 className="text-sm font-semibold text-sre-text text-left mb-3 flex items-center">
                    <span className="material-icons text-base mr-2">notes</span>
                    Notes
                  </h4>
                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs font-medium text-sre-text-muted mb-1 text-left">
                        Add note
                      </label>
                      <textarea
                        value={activeIncidentDraft.note ?? ""}
                        onChange={(e) =>
                          setIncidentDrafts((prev) => ({
                            ...prev,
                            [activeIncident.id]: {
                              ...(prev[activeIncident.id] || {}),
                              note: e.target.value,
                            },
                          }))
                        }
                        onKeyDown={(e) => {
                          
                          if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                            e.preventDefault();
                            if (canUpdateIncidents)
                              handleAddNote(activeIncident.id);
                          }
                        }}
                        className="w-full px-3 py-2 bg-sre-bg border border-sre-border rounded text-sre-text"
                        rows={3}
                        placeholder="Investigation updates, mitigation notes, root cause, handover details..."
                      />

                      <div className="mt-2 flex items-center justify-between gap-2">
                        <div className="text-xs text-sre-text-muted">
                          Press{" "}
                          <span className="px-1.5 py-0.5 bg-sre-surface border border-sre-border rounded">
                            Ctrl
                          </span>{" "}
                          +{" "}
                          <span className="px-1.5 py-0.5 bg-sre-surface border border-sre-border rounded">
                            Enter
                          </span>{" "}
                          to add quickly
                        </div>
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() =>
                              setIncidentDrafts((prev) => ({
                                ...prev,
                                [activeIncident.id]: {
                                  ...(prev[activeIncident.id] || {}),
                                  note: "",
                                },
                              }))
                            }
                          >
                            Clear
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => handleAddNote(activeIncident.id)}
                            disabled={
                              !canUpdateIncidents ||
                              !(activeIncidentDraft.note || "").trim()
                            }
                          >
                            Add note
                          </Button>
                        </div>
                      </div>
                    </div>

                    {Array.isArray(activeIncident.notes) &&
                      activeIncident.notes.length > 0 && (
                        <div className="p-3 border border-sre-border rounded-lg bg-sre-bg-alt">
                          <div className="flex items-center justify-between mb-2">
                            <p className="text-xs font-medium text-sre-text text-left">
                              Recent notes
                            </p>
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                className="text-xs text-sre-text-muted hover:text-sre-text flex items-center gap-2"
                                onClick={() => {
                                  
                                  const notes = activeIncident.notes
                                    .slice()
                                    .reverse()
                                    .slice(0, 10);
                                  const keys = notes.map((n) =>
                                    n.createdAt
                                      ? String(n.createdAt)
                                      : `${n.author}-${notes.indexOf(n)}`,
                                  );
                                  const allExpanded = keys.every((k) =>
                                    expandedNotes.has(k),
                                  );
                                  const next = new Set(expandedNotes);
                                  if (allExpanded) {
                                    keys.forEach((k) => next.delete(k));
                                  } else {
                                    keys.forEach((k) => next.add(k));
                                  }
                                  setExpandedNotes(next);
                                }}
                              >
                                <span className="text-xs font-medium">
                                  Expand all
                                </span>
                                <span className="sr-only">
                                  Toggle expand notes
                                </span>
                                <HelpTooltip content="Expand or collapse all note details" />
                              </button>
                              <button
                                type="button"
                                className="text-xs text-sre-text-muted hover:text-sre-text flex items-center gap-2"
                                onClick={async () => {
                                  try {
                                    const allText = activeIncident.notes
                                      .slice()
                                      .reverse()
                                      .slice(0, 10)
                                      .map((n) => {
                                        const authorLabel = resolveAuthorLabel(
                                          n.author,
                                        );
                                        return `${authorLabel} (${formatDateTime(n.createdAt)}): ${replaceUserIdsInText(n.text)}`;
                                      })
                                      .join("\n\n");
                                    await navigator.clipboard.writeText(
                                      allText,
                                    );
                                    toast.success("Copied notes to clipboard");
                                  } catch (e) {
                                    toast.error("Copy failed");
                                  }
                                }}
                              >
                                <span className="text-xs font-medium">
                                  Copy all
                                </span>
                                <span className="sr-only">Copy notes</span>
                                <HelpTooltip content="Copy all notes to clipboard" />
                              </button>
                            </div>
                          </div>

                          <div className="space-y-3 max-h-44 overflow-auto pr-2">
                            {activeIncident.notes
                              .slice()
                              .reverse()
                              .slice(0, 10)
                              .map((note, idx) => {
                                const key = note.createdAt
                                  ? String(note.createdAt)
                                  : `${note.author}-${idx}`;
                                const noteAuthorLabel = resolveAuthorLabel(
                                  note.author,
                                );
                                const displayText = replaceUserIdsInText(
                                  note.text,
                                );
                                const collapsed = !expandedNotes.has(key);
                                return (
                                  <div
                                    key={`${activeIncident.id}-modal-note-${key}`}
                                    className="p-3 bg-sre-bg rounded-lg border border-sre-border flex gap-3 items-start"
                                  >
                                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-sre-primary/20 to-sre-primary/10 text-sre-primary flex items-center justify-center font-semibold border border-sre-border/50 flex-shrink-0">
                                      {String(noteAuthorLabel || "")
                                        .split(" ")
                                        .map((s) => s[0])
                                        .slice(0, 1)
                                        .join("")
                                        .toUpperCase()}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                      <div className="flex items-center justify-between gap-3">
                                        <div className="text-xs text-sre-text truncate">
                                          <span className="font-medium text-sre-text">
                                            {noteAuthorLabel}
                                          </span>
                                          <span className="text-sre-text-muted ml-2 text-xs">
                                            · {formatDateTime(note.createdAt)}
                                          </span>
                                        </div>
                                        <div className="flex items-center gap-2">
                                          <button
                                            type="button"
                                            title="Quote into reply"
                                            className="text-sre-text-muted hover:text-sre-text"
                                            onClick={() =>
                                              setIncidentDrafts((prev) => ({
                                                ...prev,
                                                [activeIncident.id]: {
                                                  ...(prev[activeIncident.id] ||
                                                    {}),
                                                  note: `${prev[activeIncident.id]?.note || ""}"${displayText}" - ${noteAuthorLabel}\n\n`,
                                                },
                                              }))
                                            }
                                          >
                                            <span className="text-xs">
                                              Quote
                                            </span>
                                          </button>
                                          <button
                                            type="button"
                                            title="Copy note"
                                            className="text-sre-text-muted hover:text-sre-text"
                                            onClick={async () => {
                                              try {
                                                await navigator.clipboard.writeText(
                                                  displayText,
                                                );
                                                toast.success("Note copied");
                                              } catch (e) {
                                                toast.error("Copy failed");
                                              }
                                            }}
                                          >
                                            <span className="text-xs">
                                              Copy
                                            </span>
                                          </button>
                                          <button
                                            type="button"
                                            title={
                                              collapsed
                                                ? "Show more"
                                                : "Show less"
                                            }
                                            className="text-sre-text-muted hover:text-sre-text"
                                            onClick={() => {
                                              const next = new Set(
                                                expandedNotes,
                                              );
                                              if (next.has(key))
                                                next.delete(key);
                                              else next.add(key);
                                              setExpandedNotes(next);
                                            }}
                                          >
                                            <span className="text-xs">
                                              {collapsed ? "More" : "Less"}
                                            </span>
                                          </button>
                                        </div>
                                      </div>

                                      <div
                                        className={`mt-2 text-sm text-sre-text-muted ${collapsed ? "line-clamp-3" : ""}`}
                                      >
                                        {displayText}
                                      </div>
                                    </div>
                                  </div>
                                );
                              })}
                          </div>
                        </div>
                      )}

                  </div>
                </Card>
              )}

              <div className="flex items-center justify-end gap-2">
                <Button
                  variant="secondary"
                  onClick={() => {
                    setIncidentModal({ isOpen: false, incident: null });
                    setAssigneeSearch("");
                  }}
                >
                  Cancel
                </Button>
                <Button
                  onClick={() => handleSaveIncident(activeIncident)}
                  disabled={!canUpdateIncidents}
                  title={
                    !canUpdateIncidents
                      ? "Missing update:incidents permission"
                      : "Save Changes (Ctrl+S)"
                  }
                >
                  Save changes
                </Button>
              </div>
            </div>
          </Modal>
        )}
      </div>
    </div>
  );
}
