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
      </div>
    </Modal>
  );
}
