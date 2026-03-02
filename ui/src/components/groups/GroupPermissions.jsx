import PropTypes from "prop-types";
import { Alert, Checkbox } from "../ui";
import HelpTooltip from "../HelpTooltip";
import { getCategoryDescription } from "../../utils/groupManagementUtils";

export default function GroupPermissions({
  permissionsByResource,
  groupPermissions,
  togglePermission,
  addPerms,
  removePerms,
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-sre-text">
            Permissions (Optional)
          </h3>
          <HelpTooltip text="Configure action-level permissions members inherit (for example read/create/update/delete/test), grouped by resource type." />
        </div>
        <div className="flex gap-3 text-xs">
          <button
            type="button"
            onClick={() =>
              addPerms(Object.values(permissionsByResource).flat())
            }
            className="px-2 py-1 text-sre-primary hover:bg-sre-primary/10 rounded"
          >
            Select All
          </button>
          <button
            type="button"
            onClick={() =>
              removePerms(Object.values(permissionsByResource).flat())
            }
            className="px-2 py-1 text-sre-text-muted hover:bg-sre-surface rounded"
          >
            Clear All
          </button>
        </div>
      </div>

      <Alert variant="info">
        <div className="text-xs">
          Members of this group inherit action-level permissions. You can set
          least-privilege access now and refine later.
        </div>
      </Alert>

      <div className="max-h-96 overflow-y-auto space-y-3 pr-2">
        {Object.entries(permissionsByResource).map(([resource, perms]) => (
          <div
            key={resource}
            className="border border-sre-border rounded-lg p-3 bg-sre-surface/20"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <h4 className="font-semibold capitalize text-sm text-sre-text">
                  {resource}
                </h4>
                <HelpTooltip text={getCategoryDescription(resource)} />
              </div>
              <div className="flex gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => addPerms(perms)}
                  className="px-2 py-0.5 text-sre-primary hover:bg-sre-primary/10 rounded"
                >
                  Select All
                </button>
                <button
                  type="button"
                  onClick={() => removePerms(perms)}
                  className="px-2 py-0.5 text-sre-text-muted hover:bg-sre-surface rounded"
                >
                  Clear All
                </button>
              </div>
            </div>
            <div className="space-y-1.5">
              {perms.map((perm) => (
                <label
                  key={perm.id}
                  className="flex items-start gap-2 p-2 hover:bg-sre-surface/50 rounded cursor-pointer"
                >
                  <Checkbox
                    checked={groupPermissions.includes(perm.name)}
                    onChange={() => togglePermission(perm.name)}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <div className="font-medium text-sm text-sre-text break-words">
                        {perm.display_name || perm.name}
                      </div>
                      <HelpTooltip text={perm.description || perm.name} />
                    </div>
                  </div>
                </label>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

GroupPermissions.propTypes = {
  permissionsByResource: PropTypes.object.isRequired,
  groupPermissions: PropTypes.array.isRequired,
  togglePermission: PropTypes.func.isRequired,
  addPerms: PropTypes.func.isRequired,
  removePerms: PropTypes.func.isRequired,
};
