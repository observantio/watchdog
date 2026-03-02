import { Button, Input, Modal } from "../../components/ui";

export default function FolderCreatorModal({
  isOpen,
  onClose,
  folderName,
  setFolderName,
  onCreate,
}) {
  const handleCreate = () => {
    onCreate();
  };

  const handleClose = () => {
    onClose();
    setFolderName("");
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Create New Folder"
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
            Create Folder
          </Button>
        </div>
      }
    >
      <div>
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
      </div>
    </Modal>
  );
}
