import { useState, useEffect, useCallback, useRef } from "react";
import { useLocalStorage } from "../hooks";
import {
  searchDashboards,
  createDashboard,
  updateDashboard,
  deleteDashboard,
  getDatasources,
  createDatasource,
  updateDatasource,
  deleteDatasource,
  getFolders,
  createFolder,
  updateFolder,
  deleteFolder,
  toggleFolderHidden,
  getGroups,
  toggleDashboardHidden,
  toggleDatasourceHidden,
  getDashboard,
  createGrafanaBootstrapSession,
} from "../api";
import { Button, ConfirmDialog } from "../components/ui";
import PageHeader from "../components/ui/PageHeader";
import DashboardEditorModal from "../components/grafana/DashboardEditorModal";
import DatasourceEditorModal from "../components/grafana/DatasourceEditorModal";
import FolderCreatorModal from "../components/grafana/FolderCreatorModal";
import { useToast } from "../contexts/ToastContext";
import GrafanaTabs from "../components/grafana/GrafanaTabs";
import GrafanaContent from "../components/grafana/GrafanaContent";
import { useAuth } from "../contexts/AuthContext";
import { MIMIR_PROMETHEUS_URL } from "../utils/constants";
import {
  GRAFANA_DATASOURCE_TYPES as DATASOURCE_TYPES,
  overrideDashboardDatasource,
} from "../utils/grafanaUtils";
import { buildGrafanaLaunchUrl } from "../utils/grafanaLaunchUtils";

export default function GrafanaPage() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useLocalStorage(
    "grafana-active-tab",
    "dashboards",
  );
  const [dashboards, setDashboards] = useState([]);
  const [datasources, setDatasources] = useState([]);
  const [folders, setFolders] = useState([]);
  const [groups, setGroups] = useState([]);
  const [query, setQuery] = useLocalStorage("grafana-query", "");
  const [loading, setLoading] = useState(true);

  const [filters, setFilters] = useLocalStorage("grafana-filters", {
    teamId: "",
    folderKey: "__general__",
    showHidden: false,
  });

  const toast = useToast();
  const lastErrorToastRef = useRef({ key: "", ts: 0 });

  const handleApiError = useCallback(
    (e) => {
      if (!e) return;
      const detail =
        typeof e?.body?.detail === "string"
          ? e.body.detail
          : e?.body?.detail?.message;
      const message =
        typeof e?.body?.message === "string" ? e.body.message : null;
      const msg =
        detail ||
        message ||
        e?.message ||
        String(e || "Request failed");
      const key = `${e?.status || "x"}:${msg}`;
      const now = Date.now();
      if (
        lastErrorToastRef.current.key === key &&
        now - lastErrorToastRef.current.ts < 2000
      ) {
        return;
      }
      lastErrorToastRef.current = { key, ts: now };
      toast.error(msg);
    },
    [toast],
  );

  const [showDashboardEditor, setShowDashboardEditor] = useState(false);
  const [editingDashboard, setEditingDashboard] = useState(null);
  const [editorTab, setEditorTab] = useState("form");
  const [jsonContent, setJsonContent] = useState("");
  const [jsonError, setJsonError] = useState("");
  const [fileUploaded, setFileUploaded] = useState(false);
  const [dashboardForm, setDashboardForm] = useState({
    title: "",
    tags: "",
    folderId: 0,
    refresh: "30s",
    datasourceUid: "",
    useTemplating: false,
    visibility: "private",
    sharedGroupIds: [],
  });

  const [showDatasourceEditor, setShowDatasourceEditor] = useState(false);
  const [editingDatasource, setEditingDatasource] = useState(null);
  const [datasourceForm, setDatasourceForm] = useState({
    name: "",
    type: "prometheus",
    url: "",
    isDefault: false,
    access: "proxy",
    visibility: "private",
    sharedGroupIds: [],
    apiKeyId: "",
  });

  const [showFolderCreator, setShowFolderCreator] = useState(false);
  const [editingFolder, setEditingFolder] = useState(null);
  const [folderName, setFolderName] = useState("");
  const [folderVisibility, setFolderVisibility] = useState("private");
  const [folderSharedGroupIds, setFolderSharedGroupIds] = useState([]);
  const [allowDashboardWrites, setAllowDashboardWrites] = useState(false);

  const [confirmDialog, setConfirmDialog] = useState({
    isOpen: false,
    title: "",
    message: "",
    onConfirm: null,
    variant: "danger",
    confirmText: "Delete",
  });

  const [grafanaConfirmDialog, setGrafanaConfirmDialog] = useState({
    isOpen: false,
    path: null,
  });

  function openInGrafana(path) {
    setGrafanaConfirmDialog({
      isOpen: true,
      path: path,
    });
  }

  async function confirmOpenInGrafana() {
    const { path } = grafanaConfirmDialog || {};
    try {
      const bootstrap = await createGrafanaBootstrapSession(
        path || "/dashboards",
      );
      const launchUrl = bootstrap?.launch_url
        ? `${window.location.protocol}//${window.location.hostname}:8080${bootstrap.launch_url}`
        : buildGrafanaLaunchUrl({
            path,
            protocol: window.location.protocol,
            hostname: window.location.hostname,
          });
      window.open(launchUrl, "_blank", "noopener,noreferrer");
    } catch {
      const launchUrl = buildGrafanaLaunchUrl({
        path,
        protocol: window.location.protocol,
        hostname: window.location.hostname,
      });
      window.open(launchUrl, "_blank", "noopener,noreferrer");
    }
    setGrafanaConfirmDialog({ isOpen: false, path: null });
  }

  const loadGroups = useCallback(async () => {
    try {
      const groupsData = await getGroups().catch(() => []);
      setGroups(groupsData);
    } catch {
      /* silent */
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      if (activeTab === "dashboards") {
        const [dashboardsData, foldersData, datasourcesData] =
          await Promise.all([
            searchDashboards({
              query: query || undefined,
              teamId: filters.teamId || undefined,
              folderId:
                filters.folderKey === "__general__" ? 0 : undefined,
              folderUid:
                filters.folderKey &&
                filters.folderKey !== "__general__"
                  ? filters.folderKey
                  : undefined,
              showHidden: filters.showHidden,
            }).catch(() => []),
            getFolders({ showHidden: filters.showHidden }).catch(() => []),
            getDatasources().catch(() => []),
          ]);
        setDashboards(dashboardsData);
        setFolders(foldersData);
        setDatasources(datasourcesData);
      } else if (activeTab === "datasources") {
        const [datasourcesData] = await Promise.all([
          getDatasources({
            teamId: filters.teamId || undefined,
            showHidden: filters.showHidden,
          }).catch(() => []),
        ]);
        setDatasources(datasourcesData);
      } else if (activeTab === "folders") {
        const foldersData = await getFolders({
          showHidden: filters.showHidden,
        }).catch(() => []);
        setFolders(foldersData);
      }
    } catch (e) {
      handleApiError(e);
    } finally {
      setLoading(false);
    }
  }, [activeTab, query, filters, handleApiError]);

  useEffect(() => {
    loadData();
    loadGroups();
  }, [loadData, loadGroups]);

  async function onSearch(e) {
    e.preventDefault();
    loadData();
  }

  function clearFilters() {
    setFilters({ teamId: "", folderKey: "__general__", showHidden: false });
    setQuery("");
  }

  async function handleToggleDashboardHidden(dashboard) {
    const nowHidden = !dashboard.is_hidden;
    setConfirmDialog({
      isOpen: true,
      title: nowHidden ? "Hide Dashboard" : "Unhide Dashboard",
      confirmText: nowHidden ? "Hide" : "Unhide",
      message: nowHidden
        ? `Are you sure you want to hide "${dashboard.title}"? This will hide the dashboard for your account.`
        : `Are you sure you want to unhide "${dashboard.title}"? This will make the dashboard visible again for your account.`,
      variant: "danger",
      onConfirm: async () => {
        try {
          await toggleDashboardHidden(dashboard.uid, nowHidden);
          toast.success(nowHidden ? "Dashboard hidden" : "Dashboard visible");
          loadData();
        } catch (e) {
          handleApiError(e);
        }
      },
    });
  }

  async function handleToggleDatasourceHidden(datasource) {
    const nowHidden = !datasource.is_hidden;
    setConfirmDialog({
      isOpen: true,
      title: nowHidden ? "Hide Datasource" : "Unhide Datasource",
      confirmText: nowHidden ? "Hide" : "Unhide",
      message: nowHidden
        ? `Are you sure you want to hide "${datasource.name}"? This will hide the datasource for your account.`
        : `Are you sure you want to unhide "${datasource.name}"? This will make the datasource visible again for your account.`,
      variant: "danger",
      onConfirm: async () => {
        try {
          await toggleDatasourceHidden(datasource.uid, nowHidden);
          toast.success(nowHidden ? "Datasource hidden" : "Datasource visible");
          loadData();
        } catch (e) {
          handleApiError(e);
        }
      },
    });
  }

  function openDashboardEditor(dashboard = null) {
    setEditorTab("form");
    setJsonContent("");
    setJsonError("");
    setFileUploaded(false);

    if (dashboard) {
      setEditingDashboard(dashboard);

      setDashboardForm({
        title: dashboard.title || dashboard?.dashboard?.title || "",
        tags:
          dashboard.tags?.join(", ") ||
          (dashboard?.dashboard?.tags || []).join(", ") ||
          "",
        folderId: dashboard.folderId || dashboard?.dashboard?.folderId || 0,
        refresh: dashboard.refresh || dashboard?.dashboard?.refresh || "30s",
        datasourceUid: "",
        useTemplating: false,
        visibility: dashboard.visibility || "private",
        sharedGroupIds:
          dashboard.sharedGroupIds || dashboard.shared_group_ids || [],
      });

      const lightDashboardObj = dashboard?.dashboard || dashboard;
      if (lightDashboardObj) {
        try {
          setJsonContent(JSON.stringify(lightDashboardObj, null, 2));
        } catch (e) {
          /* ignore */
        }
      }

      if (dashboard?.uid) {
        (async () => {
          try {
            const full = await getDashboard(dashboard.uid).catch(() => null);
            if (full?.dashboard) {
              try {
                setJsonContent(JSON.stringify(full.dashboard, null, 2));
                setJsonError("");
                setFileUploaded(false);
              } catch (err) {
                // ignore stringify errors
              }
            }
          } catch (e) {
            /* ignore - leave datasource blank */
          }
        })();
      }
    } else {
      setEditingDashboard(null);
      setDashboardForm({
        title: "",
        tags: "",
        folderId: 0,
        refresh: "30s",
        datasourceUid: "",
        visibility: "private",
        sharedGroupIds: [],
      });
      setJsonContent(JSON.stringify({ title: "", panels: [] }, null, 2));
    }
    setShowDashboardEditor(true);
  }

  async function saveDashboard(jsonOverride = null) {
    if (!dashboardForm.datasourceUid) {
      toast.error("Select a default datasource before saving the dashboard");
      return;
    }

    try {
      let payload = null;
      if (jsonOverride) {
        let parsed;
        try {
          parsed = JSON.parse(jsonOverride);
          setJsonError("");
        } catch (err) {
          setJsonError(err.message);
          toast.error("Invalid JSON — please fix and try again");
          return;
        }

        payload = {
          dashboard: parsed.dashboard || parsed,
          folderId:
            parsed.folderId || Number.parseInt(dashboardForm.folderId, 10) || 0,
          overwrite:
            parsed.overwrite !== undefined
              ? !!parsed.overwrite
              : !!editingDashboard,
        };
      } else if (editorTab === "json") {
        if (!jsonContent || !jsonContent.trim()) {
          toast.error("JSON content is empty");
          return;
        }
        let parsed;
        try {
          parsed = JSON.parse(jsonContent);
          setJsonError("");
        } catch (err) {
          setJsonError(err.message);
          toast.error("Invalid JSON — please fix and try again");
          return;
        }

        if (parsed.dashboard || parsed?.meta || parsed?.orgId) {
          if (parsed.dashboard) {
            payload = {
              dashboard: parsed.dashboard,
              folderId:
                parsed.folderId ||
                Number.parseInt(dashboardForm.folderId, 10) ||
                0,
              overwrite:
                parsed.overwrite !== undefined
                  ? !!parsed.overwrite
                  : !!editingDashboard,
            };
          } else if (parsed?.meta && parsed.dashboard === undefined) {
            payload = {
              dashboard: parsed,
              folderId: Number.parseInt(dashboardForm.folderId, 10) || 0,
              overwrite: !!editingDashboard,
            };
          } else {
            payload = {
              dashboard: parsed,
              folderId: Number.parseInt(dashboardForm.folderId, 10) || 0,
              overwrite: !!editingDashboard,
            };
          }
        } else {
          payload = {
            dashboard: parsed,
            folderId: Number.parseInt(dashboardForm.folderId, 10) || 0,
            overwrite: !!editingDashboard,
          };
        }
      } else {
        const tags = dashboardForm.tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean);

        const selectedDatasource = datasources.find(
          (ds) => ds.uid === dashboardForm.datasourceUid,
        );

        payload = {
          dashboard: {
            title: dashboardForm.title,
            tags,
            refresh: dashboardForm.refresh,
            panels: [],
            timezone: "browser",
            schemaVersion: 16,
            editable: true,
            templating:
              selectedDatasource && dashboardForm.useTemplating
                ? {
                    list: [
                      {
                        name: "ds_default",
                        label: "Datasource",
                        type: "datasource",
                        query: selectedDatasource.type,
                        current: {
                          text: selectedDatasource.name,
                          value: selectedDatasource.uid,
                        },
                      },
                    ],
                  }
                : { list: [] },
          },
          folderId: Number.parseInt(dashboardForm.folderId, 10) || 0,
          overwrite: !!editingDashboard,
        };
      }

      if (payload && payload.dashboard && dashboardForm.datasourceUid) {
        payload.dashboard = overrideDashboardDatasource(
          payload.dashboard,
          dashboardForm.datasourceUid,
          datasources,
          Boolean(dashboardForm.useTemplating),
        );
      }

      if (payload && payload.dashboard) {
        const tagsFromForm = dashboardForm.tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean);
        if (tagsFromForm.length) payload.dashboard.tags = tagsFromForm;
      }

      const params = new URLSearchParams({
        visibility: dashboardForm.visibility,
      });
      if (
        dashboardForm.visibility === "group" &&
        dashboardForm.sharedGroupIds?.length > 0
      ) {
        dashboardForm.sharedGroupIds.forEach((gid) =>
          params.append("shared_group_ids", gid),
        );
      }

      if (editingDashboard) {
        if (payload.dashboard) {
          payload.dashboard.uid = editingDashboard.uid;
          payload.dashboard.id = null;
        }
        await updateDashboard(editingDashboard.uid, payload, params.toString());
        toast.success("Dashboard updated successfully");
      } else {
        if (payload.dashboard) {
          delete payload.dashboard.id;

          if (payload.dashboard.uid) {
            const suffix = Math.random().toString(36).slice(2, 8);
            payload.dashboard.uid = `${String(payload.dashboard.uid)}-${suffix}`;
          } else {
            delete payload.dashboard.uid;
          }
        }

        await createDashboard(payload, params.toString());
        toast.success("Dashboard created successfully");
      }

      setShowDashboardEditor(false);
      loadData();
    } catch (e) {
      handleApiError(e);
    }
  }

  function handleDeleteDashboard(dashboard) {
    setConfirmDialog({
      isOpen: true,
      title: "Delete Dashboard",
      message: `Are you sure you want to delete "${dashboard.title}"? This action cannot be undone.`,
      variant: "danger",
      onConfirm: async () => {
        try {
          await deleteDashboard(dashboard.uid);
          toast.success("Dashboard deleted successfully");
          loadData();
        } catch (e) {
          handleApiError(e);
        }
      },
    });
  }

  function openDatasourceEditor(datasource = null) {
    if (datasource) {
      const currentOrg = datasource.orgId || datasource.org_id || "";
      const matchedKey = (user?.api_keys || []).find(
        (k) => String(k.key) === String(currentOrg),
      );
      const defaultKey =
        (user?.api_keys || []).find((k) => k.is_default) ||
        (user?.api_keys || [])[0];
      setEditingDatasource(datasource);
      setDatasourceForm({
        name: datasource.name || "",
        type: datasource.type || "prometheus",
        url: datasource.url || "",
        isDefault: datasource.isDefault || false,
        access: datasource.access || "proxy",
        visibility: datasource.visibility || datasource.visibility || "private",
        sharedGroupIds:
          datasource.sharedGroupIds || datasource.shared_group_ids || [],
        apiKeyId: matchedKey?.id || defaultKey?.id || "",
      });
    } else {
      const dk =
        (user?.api_keys || []).find((k) => k.is_default) ||
        (user?.api_keys || [])[0];
      setEditingDatasource(null);
      setDatasourceForm({
        name: "Mimir",
        type: "prometheus",
        url: MIMIR_PROMETHEUS_URL,
        isDefault: false,
        access: "proxy",
        visibility: "private",
        sharedGroupIds: [],
        apiKeyId: dk?.id || "",
      });
    }
    setShowDatasourceEditor(true);
  }

  async function saveDatasource() {
    const isMultiTenantType = ["prometheus", "loki", "tempo"].includes(
      datasourceForm.type,
    );
    if (isMultiTenantType && !datasourceForm.apiKeyId) {
      toast.error(
        "API key is required for Prometheus, Loki, and Tempo datasources",
      );
      return;
    }

    try {
      const payload = {
        name: datasourceForm.name,
        type: datasourceForm.type,
        url: datasourceForm.url,
        access: datasourceForm.access,
        isDefault: datasourceForm.isDefault,
        jsonData: {},
      };

      if (isMultiTenantType) {
        const selectedKey = (user?.api_keys || []).find(
          (k) => k.id === datasourceForm.apiKeyId,
        );
        payload.org_id = selectedKey?.key || user?.org_id || "default";
      }

      const params = new URLSearchParams({
        visibility: datasourceForm.visibility,
      });
      if (
        datasourceForm.visibility === "group" &&
        datasourceForm.sharedGroupIds?.length > 0
      ) {
        datasourceForm.sharedGroupIds.forEach((gid) =>
          params.append("shared_group_ids", gid),
        );
      }

      if (editingDatasource) {
        await updateDatasource(
          editingDatasource.uid,
          payload,
          params.toString(),
        );
        toast.success("Datasource updated successfully");
      } else {
        await createDatasource(payload, params.toString());
        toast.success("Datasource created successfully");
      }

      setShowDatasourceEditor(false);
      loadData();
    } catch (e) {
      handleApiError(e);
    }
  }

  function handleDeleteDatasource(datasource) {
    setConfirmDialog({
      isOpen: true,
      title: "Delete Datasource",
      message: `Are you sure you want to delete "${datasource.name}"? This will affect all dashboards using this datasource.`,
      variant: "danger",
      onConfirm: async () => {
        try {
          await deleteDatasource(datasource.uid);
          toast.success("Datasource deleted successfully");
          loadData();
        } catch (e) {
          handleApiError(e);
        }
      },
    });
  }

  function openFolderEditor(folder = null) {
    if (folder) {
      setEditingFolder(folder);
      setFolderName(folder.title || "");
      setFolderVisibility(folder.visibility || "private");
      setFolderSharedGroupIds(folder.sharedGroupIds || folder.shared_group_ids || []);
      setAllowDashboardWrites(
        Boolean(
          folder.allowDashboardWrites ?? folder.allow_dashboard_writes ?? false,
        ),
      );
    } else {
      setEditingFolder(null);
      setFolderName("");
      setFolderVisibility("private");
      setFolderSharedGroupIds([]);
      setAllowDashboardWrites(false);
    }
    setShowFolderCreator(true);
  }

  async function handleCreateFolder() {
    if (!folderName.trim()) return;
    try {
      const params = new URLSearchParams({
        visibility: folderVisibility,
      });
      if (folderVisibility === "group" && folderSharedGroupIds.length > 0) {
        folderSharedGroupIds.forEach((gid) =>
          params.append("shared_group_ids", gid),
        );
      }
      if (editingFolder?.uid) {
        await updateFolder(
          editingFolder.uid,
          {
            title: folderName.trim(),
            allowDashboardWrites: allowDashboardWrites,
          },
          params.toString(),
        );
        toast.success("Folder updated successfully");
      } else {
        await createFolder(
          folderName.trim(),
          params.toString(),
          allowDashboardWrites,
        );
        toast.success("Folder created successfully");
      }
      setShowFolderCreator(false);
      setEditingFolder(null);
      setFolderName("");
      setFolderVisibility("private");
      setFolderSharedGroupIds([]);
      setAllowDashboardWrites(false);
      loadData();
    } catch (e) {
      handleApiError(e);
    }
  }

  function handleDeleteFolder(folder) {
    setConfirmDialog({
      isOpen: true,
      title: "Delete Folder",
      message: `Are you sure you want to delete "${folder.title}"? All dashboards in this folder will be moved to General.`,
      variant: "danger",
      onConfirm: async () => {
        try {
          await deleteFolder(folder.uid);
          toast.success("Folder deleted successfully");
          loadData();
        } catch (e) {
          handleApiError(e);
        }
      },
    });
  }

  async function handleToggleFolderHidden(folder) {
    const nowHidden = !folder.is_hidden;
    setConfirmDialog({
      isOpen: true,
      title: nowHidden ? "Hide Folder" : "Unhide Folder",
      confirmText: nowHidden ? "Hide" : "Unhide",
      message: nowHidden
        ? `Are you sure you want to hide "${folder.title}"? This will hide the folder and its dashboards for your account.`
        : `Are you sure you want to unhide "${folder.title}"? This will make the folder visible again for your account.`,
      variant: "danger",
      onConfirm: async () => {
        try {
          await toggleFolderHidden(folder.uid, nowHidden);
          toast.success(nowHidden ? "Folder hidden" : "Folder visible");
          loadData();
        } catch (e) {
          handleApiError(e);
        }
      },
    });
  }

  function getDatasourceIcon(type) {
    const found = DATASOURCE_TYPES.find((t) => t.value === type);
    return found ? found.icon : "🔧";
  }

  const hasActiveFilters = filters.teamId || filters.folderKey || filters.showHidden;

  return (
    <div className="animate-fade-in">
      <PageHeader
        icon="dashboard"
        title="Grafana"
        subtitle="Create and manage dashboards, datasources, and folders"
      >
        <Button
          onClick={() => openInGrafana("/")}
          size="sm"
          className="flex items-center gap-2"
          title="Open Grafana in new tab"
        >
          <span className="material-icons text-sm">open_in_new</span>
          Open Grafana
        </Button>
      </PageHeader>

      <GrafanaTabs activeTab={activeTab} onChange={setActiveTab} />

      <GrafanaContent
        loading={loading}
        activeTab={activeTab}
        dashboards={dashboards}
        datasources={datasources}
        folders={folders}
        groups={groups}
        query={query}
        setQuery={setQuery}
        filters={filters}
        setFilters={setFilters}
        onSearch={onSearch}
        onClearFilters={clearFilters}
        hasActiveFilters={hasActiveFilters}
        openDashboardEditor={openDashboardEditor}
        onOpenGrafana={openInGrafana}
        onDeleteDashboard={handleDeleteDashboard}
        onToggleDashboardHidden={handleToggleDashboardHidden}
        openDatasourceEditor={openDatasourceEditor}
        onDeleteDatasource={handleDeleteDatasource}
        onToggleDatasourceHidden={handleToggleDatasourceHidden}
        getDatasourceIcon={getDatasourceIcon}
        onCreateFolder={() => openFolderEditor(null)}
        onEditFolder={openFolderEditor}
        onDeleteFolder={handleDeleteFolder}
        onToggleFolderHidden={handleToggleFolderHidden}
      />

      <DashboardEditorModal
        isOpen={showDashboardEditor}
        onClose={() => setShowDashboardEditor(false)}
        editingDashboard={editingDashboard}
        dashboardForm={dashboardForm}
        setDashboardForm={setDashboardForm}
        editorTab={editorTab}
        setEditorTab={setEditorTab}
        jsonContent={jsonContent}
        setJsonContent={setJsonContent}
        jsonError={jsonError}
        setJsonError={setJsonError}
        fileUploaded={fileUploaded}
        setFileUploaded={setFileUploaded}
        folders={folders}
        datasources={datasources}
        groups={groups}
        onSave={saveDashboard}
      />

      <DatasourceEditorModal
        isOpen={showDatasourceEditor}
        onClose={() => setShowDatasourceEditor(false)}
        editingDatasource={editingDatasource}
        datasourceForm={datasourceForm}
        setDatasourceForm={setDatasourceForm}
        user={user}
        groups={groups}
        onSave={saveDatasource}
      />

      <FolderCreatorModal
        isOpen={showFolderCreator}
        onClose={() => {
          setShowFolderCreator(false);
          setEditingFolder(null);
          setFolderName("");
          setFolderVisibility("private");
          setFolderSharedGroupIds([]);
          setAllowDashboardWrites(false);
        }}
        editingFolder={editingFolder}
        folderName={folderName}
        setFolderName={setFolderName}
        folderVisibility={folderVisibility}
        setFolderVisibility={setFolderVisibility}
        folderSharedGroupIds={folderSharedGroupIds}
        setFolderSharedGroupIds={setFolderSharedGroupIds}
        allowDashboardWrites={allowDashboardWrites}
        setAllowDashboardWrites={setAllowDashboardWrites}
        groups={groups}
        onCreate={handleCreateFolder}
      />

      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        onClose={() => setConfirmDialog({ ...confirmDialog, isOpen: false })}
        onConfirm={confirmDialog.onConfirm || (() => {})}
        title={confirmDialog.title}
        message={confirmDialog.message}
        variant={confirmDialog.variant || "danger"}
        confirmText={confirmDialog.confirmText || "Delete"}
        cancelText="Cancel"
      />

      <ConfirmDialog
        isOpen={grafanaConfirmDialog.isOpen}
        onClose={() => setGrafanaConfirmDialog({ isOpen: false, path: null })}
        onConfirm={confirmOpenInGrafana}
        title="Open in Grafana"
        message="This will proxy through Be Observant to get a secure, scoped, authenticated, and restricted view of what you can view and share under Grafana. If you want full admin access, please contact an admin and you can log into Grafana directly with a different username and password."
        variant="primary"
        confirmText="Continue to Grafana"
        cancelText="Cancel"
      />
    </div>
  );
}
