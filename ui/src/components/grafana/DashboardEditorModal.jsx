import { useState } from "react";
import { Button, Input, Modal, Select } from "../../components/ui";
import HelpTooltip from "../../components/HelpTooltip";
import VisibilitySelector from "./VisibilitySelector";
import DatasourceSelector from "./DatasourceSelector";
import { GRAFANA_REFRESH_INTERVALS } from "../../utils/constants";
import { DASHBOARD_TEMPLATES } from "./dashboardTemplates";

export default function DashboardEditorModal({
  isOpen,
  onClose,
  editingDashboard,
  dashboardForm,
  setDashboardForm,
  editorTab,
  setEditorTab,
  jsonContent,
  setJsonContent,
  jsonError,
  setJsonError,
  fileUploaded,
  setFileUploaded,
  folders,
  datasources,
  groups,
  onSave,
}) {
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [showJsonConflict, setShowJsonConflict] = useState(false);

  const applyTemplate = (template) => {
    setSelectedTemplate(template.id);
    setJsonContent(JSON.stringify(template.dashboard, null, 2));
    setJsonError("");
    setFileUploaded(false);
  };

  const _jsonLooksMeaningful = (content) => {
    if (!content || !content.trim()) return false;
    try {
      const parsed = JSON.parse(content);
      const db = parsed.dashboard || parsed;
      if (fileUploaded) return true;
      if (editingDashboard) return true;
      if (db && Array.isArray(db.panels) && db.panels.length > 0) return true;
      if (db && typeof db.title === "string" && db.title.trim().length > 0)
        return true;
      return false;
    } catch (e) {
      return true;
    }
  };

  const mergeFormIntoJson = (rawJson) => {
    let parsed;
    try {
      parsed = JSON.parse(rawJson);
    } catch (e) {
      parsed = {};
    }

    const db = parsed.dashboard || parsed;
    const tags = (dashboardForm.tags || "")
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    const selectedDatasource = datasources.find(
      (ds) => ds.uid === dashboardForm.datasourceUid,
    );
    db.title = dashboardForm.title;
    db.refresh = dashboardForm.refresh;
    db.tags = tags;
    db.timezone = db.timezone || "browser";

    db.templating =
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
        : db.templating || { list: [] };

    if (parsed.dashboard) {
      parsed.dashboard = db;
      return parsed;
    }
    return db;
  };

  const overrideJsonWithForm = () => {
    const tags = (dashboardForm.tags || "")
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);

    const selectedDatasource = datasources.find(
      (ds) => ds.uid === dashboardForm.datasourceUid,
    );

    const dashboardObj = {
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
    };

    const str = JSON.stringify(dashboardObj, null, 2);
    setJsonContent(str);
    onSave(str);
  };

  const updateJsonWithForm = () => {
    const merged = mergeFormIntoJson(jsonContent || "{}");
    const str = JSON.stringify(merged, null, 2);
    setJsonContent(str);
    onSave(str);
  };

  const handleSave = () => {
    if (editorTab === "form" && _jsonLooksMeaningful(jsonContent)) {
      setShowJsonConflict(true);
      return;
    }
    onSave();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      closeOnOverlayClick={false}
      title={editingDashboard ? "Edit Dashboard" : "Create New Dashboard"}
      size="md"
      footer={
        <div className="flex gap-3 justify-end">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={
              !dashboardForm.datasourceUid ||
              (editorTab === "form"
                ? !dashboardForm.title.trim()
                : !jsonContent.trim() || !!jsonError)
            }
          >
            {editingDashboard ? "Update Dashboard" : "Create Dashboard"}
          </Button>
        </div>
      }
    >
      <div>
        <div
          className="flex gap-1 mb-4 justify-center bg-sre-bg-alt/80 rounded-xl p-1"
          role="tablist"
          aria-label="Dashboard editor mode"
        >
          <button
            type="button"
            role="tab"
            aria-selected={editorTab === "form"}
            className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-sre-primary/50 inline-flex items-center gap-2 ${
              editorTab === "form"
                ? "bg-sre-primary text-white shadow-sm"
                : "bg-transparent text-sre-text-muted hover:text-sre-text hover:bg-sre-surface/70"
            }`}
            onClick={() => setEditorTab("form")}
          >
            <span
              className={`w-6 h-6 rounded-full inline-flex items-center justify-center ${
                editorTab === "form"
                  ? "bg-white/20 text-white"
                  : "bg-sre-surface text-sre-text-muted"
              }`}
            >
              <span className="material-icons text-[14px]">edit_note</span>
            </span>
            Form
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={editorTab === "json"}
            className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-sre-primary/50 inline-flex items-center gap-2 ${
              editorTab === "json"
                ? "bg-sre-primary text-white shadow-sm"
                : "bg-transparent text-sre-text-muted hover:text-sre-text hover:bg-sre-surface/70"
            }`}
            onClick={() => setEditorTab("json")}
          >
            <span
              className={`w-6 h-6 rounded-full inline-flex items-center justify-center ${
                editorTab === "json"
                  ? "bg-white/20 text-white"
                  : "bg-sre-surface text-sre-text-muted"
              }`}
            >
              <span className="material-icons text-[14px]">data_object</span>
            </span>
            JSON
          </button>
        </div>

        {editorTab === "form" && (
          <div className="space-y-4">
            {showJsonConflict && (
              <div className="p-5 mb-4 rounded-xl border-2 border-red-600 border-dashed">
                <div className="flex flex-col sm:flex-row sm:justify-between gap-4">
                  <div className="flex-1">
                    <div className="text-base font-semibold text-sre-text mb-1">
                      JSON content detected
                    </div>
                    <div className="text-sm text-sre-text-muted mb-3">
                      You previously edited or uploaded dashboard JSON. Choose
                      how to proceed:
                    </div>
                    <ul className="list-disc list-inside text-sm text-sre-text-muted space-y-1">
                      <li>
                        <strong>Fresh Start</strong> — replace the JSON with
                        values from the form.
                      </li>
                      <li>
                        <strong>Update JSON</strong> — keep panels/layout from
                        JSON but update title, tags, datasource, and refresh
                        from the form.
                      </li>
                      <li>
                        <strong>Cancel Edit</strong> — return to editing without
                        saving.
                      </li>
                    </ul>
                  </div>

                  <div className="flex flex-col sm:items-end gap-2 mt-3 sm:mt-0">
                    <button
                      data-testid="json-conflict-override"
                      type="button"
                      className="px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-medium hover:bg-red-700 transition-colors"
                      onClick={() => {
                        setShowJsonConflict(false);
                        overrideJsonWithForm();
                      }}
                    >
                      Fresh Start
                    </button>
                    <button
                      data-testid="json-conflict-merge"
                      type="button"
                      className="px-4 py-2 rounded-lg bg-sre-primary text-white text-sm font-medium hover:bg-sre-primary/90 transition-colors"
                      onClick={() => {
                        setShowJsonConflict(false);
                        updateJsonWithForm();
                      }}
                    >
                      Update JSON
                    </button>
                    <button
                      data-testid="json-conflict-cancel"
                      type="button"
                      className="px-4 py-2 rounded-lg border border-sre-border bg-transparent text-sm font-medium hover:bg-sre-bg-alt transition-colors"
                      onClick={() => setShowJsonConflict(false)}
                    >
                      Cancel Edit
                    </button>
                  </div>
                </div>
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Dashboard Title <span className="text-red-500">*</span>{" "}
                <HelpTooltip text="Enter a descriptive title for your dashboard." />
              </label>
              <Input
                value={dashboardForm.title}
                onChange={(e) =>
                  setDashboardForm({ ...dashboardForm, title: e.target.value })
                }
                placeholder="My Awesome Dashboard"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Tags (comma-separated)
              </label>
              <Input
                value={dashboardForm.tags}
                onChange={(e) =>
                  setDashboardForm({ ...dashboardForm, tags: e.target.value })
                }
                placeholder="production, metrics, monitoring"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Folder
              </label>
              <Select
                value={dashboardForm.folderId}
                onChange={(e) =>
                  setDashboardForm({
                    ...dashboardForm,
                    folderId: e.target.value,
                  })
                }
              >
                <option value="0">General</option>
                {folders.map((folder) => (
                  <option key={folder.id} value={folder.id}>
                    {folder.title}
                  </option>
                ))}
              </Select>
            </div>
            <DatasourceSelector
              datasourceUid={dashboardForm.datasourceUid}
              onDatasourceChange={(v) =>
                setDashboardForm({ ...dashboardForm, datasourceUid: v })
              }
              datasources={datasources}
            />
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Auto-refresh
              </label>
              <Select
                value={dashboardForm.refresh}
                onChange={(e) =>
                  setDashboardForm({
                    ...dashboardForm,
                    refresh: e.target.value,
                  })
                }
              >
                {GRAFANA_REFRESH_INTERVALS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="border-t border-sre-border pt-4">
              <label className="block text-sm font-medium text-sre-text mb-2">
                Visibility
              </label>
              <VisibilitySelector
                visibility={dashboardForm.visibility}
                onVisibilityChange={(value) =>
                  setDashboardForm({
                    ...dashboardForm,
                    visibility: value,
                    sharedGroupIds: [],
                  })
                }
                sharedGroupIds={dashboardForm.sharedGroupIds}
                onSharedGroupIdsChange={(ids) =>
                  setDashboardForm({ ...dashboardForm, sharedGroupIds: ids })
                }
                groups={groups}
              />
            </div>
          </div>
        )}

        {editorTab === "json" && (
          <div className="space-y-4">
            {/* Templates picker */}
            <div className="">
              <div className="mb-3 flex items-center gap-3">
                <div>
                  <h4 className="text-base font-semibold text-sre-text">
                    Templates
                  </h4>
                  <p className="text-sm text-sre-text-muted">
                    Choose a starting dashboard template — click a card to load
                    it into the editor.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 overflow-y-auto max-h-80 ">
                {DASHBOARD_TEMPLATES.map((t) => {
                  const isSelected = selectedTemplate === t.id;
                  const panelTitles =
                    (t.dashboard.panels || [])
                      .map((p) => p.title)
                      .slice(0, 3)
                      .join("\n") || "This is either a template with no panels or a complex dashboard where panel titles are not easily extracted.";
                  return (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => applyTemplate(t)}
                      className={`text-left p-3 rounded-lg border-2 transition-all duration-200 group shadow-sm hover:shadow-md ${
                        isSelected
                          ? "border-sre-primary bg-sre-primary/10 shadow-md"
                          : "border-sre-border bg-sre-surface hover:border-sre-primary hover:bg-sre-primary/5"
                      }`}
                      data-testid={`load-template-${t.id}`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div
                          className={`text-base font-semibold ${isSelected ? "text-sre-primary" : "text-sre-text"}`}
                        >
                          {t.name}
                        </div>
                        <span className="material-icons text-sre-text-muted">
                          {t.icon}
                        </span>
                      </div>
                      <div className="text-sm text-sre-text-muted mb-3 line-clamp-3">
                        {t.summary}
                      </div>
                      <div className="text-xs font-mono text-sre-text-muted bg-sre-bg-alt p-2 rounded border whitespace-pre-wrap leading-relaxed min-h-[48px] overflow-hidden">
                        {panelTitles}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-sre-text mb-3">
                Upload JSON file
              </label>
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <input
                    type="file"
                    accept="application/json,.json"
                    onChange={async (e) => {
                      const f = e.target.files && e.target.files[0];
                      if (!f) return;
                      try {
                        const txt = await f.text();
                        setJsonContent(txt);
                        setJsonError("");
                        setFileUploaded(true);
                      } catch (err) {
                        setJsonError("Failed to read file");
                        setFileUploaded(false);
                      }
                    }}
                    className="hidden"
                    id="json-file-upload"
                  />
                  <label
                    htmlFor="json-file-upload"
                    className="inline-flex items-center gap-2 px-4 py-2 border border-sre-border rounded-lg bg-sre-surface hover:bg-sre-surface-light text-sre-text cursor-pointer transition-colors"
                  >
                    <span className="material-icons text-sm">upload_file</span>
                    Choose File
                  </label>

                  <span className="text-sm text-sre-text-muted">
                    {fileUploaded ? "File loaded" : "No file chosen"}
                  </span>
                </div>
                <p className="text-sm text-sre-text-muted">
                  You can upload a Grafana-exported JSON or paste a dashboard
                  object in the editor below.
                </p>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Dashboard JSON
              </label>
              <textarea
                className="w-full min-h-[220px] p-3 border rounded bg-sre-bg"
                value={jsonContent}
                onChange={(e) => setJsonContent(e.target.value)}
                placeholder="Paste dashboard JSON here (export from Grafana or raw dashboard object)"
              />
              {jsonError && (
                <p className="text-sm text-red-500 mt-2">
                  JSON error: {jsonError}
                </p>
              )}
            </div>
            <div className="border-t border-sre-border pt-4">
              <label className="block text-sm font-medium text-sre-text mb-2">
                Folder
              </label>
              <Select
                value={dashboardForm.folderId}
                onChange={(e) =>
                  setDashboardForm({
                    ...dashboardForm,
                    folderId: e.target.value,
                  })
                }
              >
                <option value="0">General</option>
                {folders.map((folder) => (
                  <option key={folder.id} value={folder.id}>
                    {folder.title}
                  </option>
                ))}
              </Select>

              <div className="mt-4">
                <DatasourceSelector
                  datasourceUid={dashboardForm.datasourceUid}
                  onDatasourceChange={(v) =>
                    setDashboardForm({ ...dashboardForm, datasourceUid: v })
                  }
                  datasources={datasources}
                />
              </div>

              <div className="mt-4">
                <label className="block text-sm font-medium text-sre-text mb-2">
                  Tags (comma-separated)
                </label>
                <Input
                  value={dashboardForm.tags}
                  onChange={(e) =>
                    setDashboardForm({ ...dashboardForm, tags: e.target.value })
                  }
                  placeholder="production, metrics, monitoring"
                />
              </div>

              <div className="mt-4">
                <label className="block text-sm font-medium text-sre-text mb-2">
                  Visibility
                </label>
                <VisibilitySelector
                  visibility={dashboardForm.visibility}
                  onVisibilityChange={(value) =>
                    setDashboardForm({
                      ...dashboardForm,
                      visibility: value,
                      sharedGroupIds: [],
                    })
                  }
                  sharedGroupIds={dashboardForm.sharedGroupIds}
                  onSharedGroupIdsChange={(ids) =>
                    setDashboardForm({ ...dashboardForm, sharedGroupIds: ids })
                  }
                  groups={groups}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
