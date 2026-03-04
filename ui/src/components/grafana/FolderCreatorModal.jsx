import { Button, Input, Modal } from "../../components/ui";
import VisibilitySelector from "./VisibilitySelector";

export default function FolderCreatorModal({
  isOpen,
  onClose,
  editingFolder,
  folderName,
  setFolderName,
  folderVisibility,
  setFolderVisibility,
  folderSharedGroupIds,
  setFolderSharedGroupIds,
  allowDashboardWrites,
  setAllowDashboardWrites,
  groups,
  onCreate,
}) {
  const handleCreate = () => {
    onCreate();
  };

  const handleClose = () => {
    onClose();
    setFolderName("");
    setFolderVisibility("private");
    setFolderSharedGroupIds([]);
    setAllowDashboardWrites(false);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={editingFolder ? "Edit Folder" : "Create New Folder"}
      size="sm"
      footer={
        <div className="flex gap-3 justify-end">
          <Button variant="ghost" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleCreate}
            disabled={!folderName.trim()}
          >
            {editingFolder ? "Update Folder" : "Create Folder"}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <label className="block text-sm font-medium text-sre-text mb-2">
          Folder Name <span className="text-red-500">*</span>
        </label>
        <Input
          value={folderName}
          onChange={(e) => setFolderName(e.target.value)}
          placeholder="Production Dashboards"
          required
          autoFocus
          onKeyDown={(e) => {
            if (e.key === "Enter" && folderName.trim()) handleCreate();
          }}
        />
        <div>
          <label className="block text-sm font-medium text-sre-text mb-2">
            Visibility
          </label>
          <VisibilitySelector
            visibility={folderVisibility}
            onVisibilityChange={(value) => {
              setFolderVisibility(value);
              setFolderSharedGroupIds([]);
            }}
            sharedGroupIds={folderSharedGroupIds}
            onSharedGroupIdsChange={setFolderSharedGroupIds}
            groups={groups || []}
          />
        </div>
        <label className="flex items-start gap-3 rounded-lg border border-sre-border/40 p-3">
          <input
            type="checkbox"
            checked={!!allowDashboardWrites}
            onChange={(e) => setAllowDashboardWrites(e.target.checked)}
            className="mt-0.5"
          />
          <div>
            <div className="text-sm font-medium text-sre-text">
              Allow members to add dashboards
            </div>
            <div className="text-xs text-sre-text-muted">
              When enabled, users with access to this folder can upload/create dashboards inside it.
              Folder edit/delete remains owner-only.
            </div>
          </div>
        </label>
      </div>
    </Modal>
  );
}
