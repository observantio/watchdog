import { useEffect } from "react";
import { Button, Input, Modal, Select } from "../../components/ui";
import VisibilitySelector from "./VisibilitySelector";
import { GRAFANA_DATASOURCE_TYPES as DATASOURCE_TYPES } from "../../utils/grafanaUtils";
import {
  MIMIR_PROMETHEUS_URL,
  LOKI_BASE,
  TEMPO_URL,
} from "../../utils/constants";

export default function DatasourceEditorModal({
  isOpen,
  onClose,
  editingDatasource,
  datasourceForm,
  setDatasourceForm,
  user,
  groups,
  onSave,
}) {
  const defaultKey =
    (user?.api_keys || []).find((k) => k.is_default) ||
    (user?.api_keys || [])[0];
  const isMultiTenantType = ["prometheus", "loki", "tempo"].includes(
    datasourceForm.type,
  );

  useEffect(() => {
    if (editingDatasource) return;
    const urlMapping = {
      prometheus: MIMIR_PROMETHEUS_URL,
      loki: LOKI_BASE,
      tempo: TEMPO_URL,
    };
    const nameMapping = {
      prometheus: "Mimir",
      loki: "Loki",
      tempo: "Tempo",
    };
    const defaultUrl = urlMapping[datasourceForm.type];
    const defaultName = nameMapping[datasourceForm.type];
    setDatasourceForm((prev) => ({
      ...prev,
      url: defaultUrl || prev.url,
      name: defaultName || prev.name,
    }));
  }, [datasourceForm.type, editingDatasource, setDatasourceForm]);

  const handleSave = () => {
    onSave();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      closeOnOverlayClick={false}
      title={editingDatasource ? "Edit Datasource" : "Create New Datasource"}
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
              !String(datasourceForm.name || "").trim() ||
              !String(datasourceForm.url || "").trim() ||
              (isMultiTenantType && !String(datasourceForm.apiKeyId || "").trim())
            }
          >
            {editingDatasource ? "Update Datasource" : "Create Datasource"}
          </Button>
        </div>
      }
    >
      <div className="space-y-6">
        <div className="space-y-4">
          <div className="pb-2 border-b border-sre-border">
            <h3 className="text-sm font-semibold text-sre-text uppercase tracking-wide">
              Basic Information
            </h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Name <span className="text-red-500">*</span>
              </label>
              <Input
                value={String(datasourceForm.name || "")}
                onChange={(e) =>
                  setDatasourceForm({ ...datasourceForm, name: e.target.value })
                }
                placeholder={
                  datasourceForm.type === "prometheus"
                    ? "Mimir"
                    : datasourceForm.type === "loki"
                      ? "My Loki"
                      : "My Tempo"
                }
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Type <span className="text-red-500">*</span>
              </label>
              <Select
                value={datasourceForm.type}
                onChange={(e) =>
                  setDatasourceForm({ ...datasourceForm, type: e.target.value })
                }
                disabled={!!editingDatasource}
              >
                {DATASOURCE_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </Select>
            </div>
          </div>
        </div>
        <div className="space-y-4">
          <div className="pb-2 border-b border-sre-border">
            <h3 className="text-sm font-semibold text-sre-text uppercase tracking-wide">
              Connection
            </h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-sre-text mb-2">
                URL <span className="text-red-500">*</span>
              </label>
              <Input
                value={String(datasourceForm.url || "")}
                onChange={(e) =>
                  setDatasourceForm({ ...datasourceForm, url: e.target.value })
                }
                placeholder={
                  datasourceForm.type === "prometheus"
                    ? MIMIR_PROMETHEUS_URL
                    : datasourceForm.type === "loki"
                      ? LOKI_BASE
                      : TEMPO_URL
                }
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Access Mode
              </label>
              <Select
                value={datasourceForm.access}
                onChange={(e) =>
                  setDatasourceForm({
                    ...datasourceForm,
                    access: e.target.value,
                  })
                }
              >
                <option value="proxy">Server (Proxy)</option>
                <option value="direct">Browser (Direct)</option>
              </Select>
            </div>
          </div>
        </div>
        {isMultiTenantType && (
            <div className="space-y-4">
              <div className="pb-2 border-b border-sre-border">
                <h3 className="text-sm font-semibold text-sre-text uppercase tracking-wide">
                  Multi-tenant Configuration
                </h3>
              </div>
              <div>
                <label className="block text-sm font-medium text-sre-text mb-2">
                  API Key <span className="text-red-500">*</span>
                </label>
                <Select
                  value={datasourceForm.apiKeyId}
                  onChange={(e) =>
                    setDatasourceForm({
                      ...datasourceForm,
                      apiKeyId: e.target.value,
                    })
                  }
                  required
                >
                  <option value="">Select API key</option>
                  {defaultKey && (
                    <option key={defaultKey.id} value={defaultKey.id}>
                      Default — {defaultKey.name}
                    </option>
                  )}
                  {(user?.api_keys || [])
                    .filter((k) => !k.is_default)
                    .map((key) => (
                      <option key={key.id} value={key.id}>
                        {key.name}
                      </option>
                    ))}
                </Select>
              </div>
            </div>
          )}
        <div className="space-y-4">
          <div className="pb-2 border-b border-sre-border">
            <h3 className="text-sm font-semibold text-sre-text uppercase tracking-wide">
              Settings
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="is-default"
              checked={datasourceForm.isDefault}
              onChange={(e) =>
                setDatasourceForm({
                  ...datasourceForm,
                  isDefault: e.target.checked,
                })
              }
              className="w-4 h-4"
            />
            <label htmlFor="is-default" className="text-sm text-sre-text">
              Set as default datasource
            </label>
          </div>
          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              Visibility
            </label>
            <VisibilitySelector
              visibility={datasourceForm.visibility}
              onVisibilityChange={(value) =>
                setDatasourceForm({
                  ...datasourceForm,
                  visibility: value,
                  sharedGroupIds: [],
                })
              }
              sharedGroupIds={datasourceForm.sharedGroupIds}
              onSharedGroupIdsChange={(ids) =>
                setDatasourceForm({ ...datasourceForm, sharedGroupIds: ids })
              }
              groups={groups}
            />
          </div>
        </div>
      </div>
    </Modal>
  );
}
