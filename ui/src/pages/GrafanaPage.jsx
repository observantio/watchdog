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
  deleteFolder,
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
  inferDashboardDatasource,
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
    showHidden: false,
  });

  const toast = useToast();
  const lastErrorToastRef = useRef({ key: "", ts: 0 });

  const handleApiError = useCallback(
    (e) => {
      if (!e) return;
      const msg =
        e?.body?.detail ||
        e?.body?.message ||
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
  const [folderName, setFolderName] = useState("");

  const [confirmDialog, setConfirmDialog] = useState({
    isOpen: false,
    title: "",
    message: "",
    onConfirm: null,
    variant: "danger",
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
              showHidden: filters.showHidden,
            }).catch(() => []),
            getFolders().catch(() => []),
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
        const foldersData = await getFolders().catch(() => []);
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
    setFilters({ teamId: "", showHidden: false });
    setQuery("");
  }

  async function handleToggleDashboardHidden(dashboard) {
    const nowHidden = !dashboard.is_hidden;
    setConfirmDialog({
      isOpen: true,
      title: nowHidden ? "Hide Dashboard" : "Unhide Dashboard",
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

      const inferred = inferDashboardDatasource(dashboard, datasources);

      setDashboardForm({
        title: dashboard.title || dashboard?.dashboard?.title || "",
        tags:
          dashboard.tags?.join(", ") ||
          (dashboard?.dashboard?.tags || []).join(", ") ||
          "",
        folderId: dashboard.folderId || dashboard?.dashboard?.folderId || 0,
        refresh: dashboard.refresh || dashboard?.dashboard?.refresh || "30s",
        datasourceUid: inferred.uid || "",
        useTemplating: Boolean(inferred.useTemplating),
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
            const inferred = inferDashboardDatasource(
              full?.dashboard || full,
              datasources,
            );
            if (inferred.uid) {
              setDashboardForm((prev) => ({
                ...prev,
                datasourceUid: inferred.uid,
                useTemplating: inferred.useTemplating,
              }));
            }

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
        apiKeyId: "",
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
    if (!editingDatasource && isMultiTenantType && !datasourceForm.apiKeyId) {
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

      if (!editingDatasource && isMultiTenantType) {
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

  async function handleCreateFolder() {
    if (!folderName.trim()) return;
    try {
      await createFolder(folderName.trim());
      toast.success("Folder created successfully");
      setShowFolderCreator(false);
      setFolderName("");
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

  function getDatasourceIcon(type) {
    const found = DATASOURCE_TYPES.find((t) => t.value === type);
    return found ? found.icon : "🔧";
  }

  const hasActiveFilters = filters.teamId || filters.showHidden;

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
        onCreateFolder={() => setShowFolderCreator(true)}
        onDeleteFolder={handleDeleteFolder}
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
          setFolderName("");
        }}
        folderName={folderName}
        setFolderName={setFolderName}
        onCreate={handleCreateFolder}
      />

      <ConfirmDialog
        isOpen={confirmDialog.isOpen}
        onClose={() => setConfirmDialog({ ...confirmDialog, isOpen: false })}
        onConfirm={confirmDialog.onConfirm || (() => {})}
        title={confirmDialog.title}
        message={confirmDialog.message}
        variant={confirmDialog.variant || "danger"}
        confirmText="Delete"
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
