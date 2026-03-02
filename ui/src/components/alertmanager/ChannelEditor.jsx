import { useState, useEffect } from "react";
import PropTypes from "prop-types";
import { Button, Input, Select } from "../ui";
import HelpTooltip from "../HelpTooltip";
import { getGroups } from "../../api";
import EmailChannelFields from "./channelForms/EmailChannelFields";

/**
 * ChannelEditor component with group/user scoping
 * @param {object} props - Component props
 */
export default function ChannelEditor({
  channel,
  onSave,
  onCancel,
  allowedTypes = [],
  visibility = "private",
}) {
  const incomingSharedGroupIds =
    channel?.sharedGroupIds || channel?.shared_group_ids || [];
  const [formData, setFormData] = useState(
    channel || {
      name: "",
      type: "webhook",
      enabled: true,
      config: {},
      // visibility is controlled by the Integrations page tab (passed in via `visibility` prop)
      visibility: channel?.visibility || visibility,
      sharedGroupIds: incomingSharedGroupIds,
    },
  );
  const [groups, setGroups] = useState([]);
  const [selectedGroups, setSelectedGroups] = useState(
    new Set(incomingSharedGroupIds),
  );

  useEffect(() => {
    loadGroups();
  }, []);

  useEffect(() => {
    if (channel) {
      const normalizedSharedGroupIds =
        channel.sharedGroupIds || channel.shared_group_ids || [];
      setFormData({
        ...channel,
        visibility: channel.visibility || visibility,
        sharedGroupIds: normalizedSharedGroupIds,
      });
      setSelectedGroups(new Set(normalizedSharedGroupIds));
      return;
    }

    setFormData({
      name: "",
      type: "webhook",
      enabled: true,
      config: {},
      visibility,
      sharedGroupIds: [],
    });
    setSelectedGroups(new Set());
  }, [channel, visibility]);

  const loadGroups = async () => {
    try {
      const groupsData = await getGroups();
      setGroups(groupsData);
    } catch {
      // Silently handle
    }
  };

  const toggleGroup = (groupId) => {
    const newGroups = new Set(selectedGroups);
    if (newGroups.has(groupId)) {
      newGroups.delete(groupId);
    } else {
      newGroups.add(groupId);
    }
    setSelectedGroups(newGroups);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave({
      ...formData,
      sharedGroupIds: Array.from(selectedGroups),
    });
  };

  const renderConfigFields = () => {
    switch (formData.type) {
      case "email":
        return (
          <EmailChannelFields formData={formData} setFormData={setFormData} />
        );
      case "slack":
        return (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Webhook URL{" "}
                <HelpTooltip text="The Slack webhook URL for sending notifications to your Slack channel." />
              </label>
              <Input
                value={
                  formData.config.webhookUrl ||
                  formData.config.webhook_url ||
                  ""
                }
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    config: {
                      ...formData.config,
                      webhookUrl: e.target.value,
                      webhook_url: e.target.value,
                    },
                  })
                }
                placeholder="https://hooks.slack.com/services/..."
                required
                className="bg-sre-bg border-sre-border/60 focus:border-sre-primary"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Channel{" "}
                <HelpTooltip text="The Slack channel name where notifications will be posted (optional, can be overridden in webhook)." />
              </label>
              <Input
                value={formData.config.channel || ""}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    config: { ...formData.config, channel: e.target.value },
                  })
                }
                placeholder="#alerts"
                className="bg-sre-bg border-sre-border/60 focus:border-sre-primary"
              />
            </div>
          </div>
        );
      case "teams":
        return (
          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              Webhook URL{" "}
              <HelpTooltip text="The Microsoft Teams webhook URL for sending notifications to your Teams channel." />
            </label>
            <Input
              value={
                formData.config.webhookUrl || formData.config.webhook_url || ""
              }
              onChange={(e) =>
                setFormData({
                  ...formData,
                  config: {
                    ...formData.config,
                    webhookUrl: e.target.value,
                    webhook_url: e.target.value,
                  },
                })
              }
              placeholder="https://outlook.office.com/webhook/..."
              required
              className="bg-sre-bg border-sre-border/60 focus:border-sre-primary"
            />
          </div>
        );
      case "webhook":
        return (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                Webhook URL{" "}
                <HelpTooltip text="The HTTP endpoint URL where alert notifications will be sent." />
              </label>
              <Input
                value={formData.config.url || ""}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    config: { ...formData.config, url: e.target.value },
                  })
                }
                placeholder="https://example.com/webhook"
                required
                className="bg-sre-bg border-sre-border/60 focus:border-sre-primary"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                HTTP Method{" "}
                <HelpTooltip text="The HTTP method to use when sending the webhook request." />
              </label>
              <Select
                value={formData.config.method || "POST"}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    config: { ...formData.config, method: e.target.value },
                  })
                }
                className="bg-sre-bg border-sre-border/60 focus:border-sre-primary"
              >
                <option value="POST">POST</option>
                <option value="PUT">PUT</option>
              </Select>
            </div>
          </div>
        );

      case "pagerduty":
        return (
          <div>
            <label className="block text-sm font-medium text-sre-text mb-2">
              Integration Key{" "}
              <HelpTooltip text="Your PagerDuty integration key (also called routing key) for sending alerts to PagerDuty." />
            </label>
            <Input
              value={
                formData.config.integrationKey ||
                formData.config.routing_key ||
                ""
              }
              onChange={(e) =>
                setFormData({
                  ...formData,
                  config: {
                    ...formData.config,
                    integrationKey: e.target.value,
                    routing_key: e.target.value,
                  },
                })
              }
              placeholder="Your PagerDuty integration key"
              required
              className="bg-sre-bg border-sre-border/60 focus:border-sre-primary"
            />
          </div>
        );

      default:
        return null;
    }
  };

  const channelTypeOptions = [
    {
      value: "email",
      label: "Email",
      icon: "email",
      description: "Send notifications via email",
    },
    {
      value: "slack",
      label: "Slack",
      icon: "chat",
      description: "Post messages to Slack channels",
    },
    {
      value: "teams",
      label: "Microsoft Teams",
      icon: "groups",
      description: "Send notifications to Teams channels",
    },
    {
      value: "webhook",
      label: "Webhook",
      icon: "link",
      description: "Send HTTP requests to custom endpoints",
    },
    {
      value: "pagerduty",
      label: "PagerDuty",
      icon: "notifications_active",
      description: "Create incidents in PagerDuty",
    },
  ].filter((item) => {
    if (!Array.isArray(allowedTypes) || allowedTypes.length === 0) return true;
    return allowedTypes.includes(item.value);
  });

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Basic Information Section */}
      <div className="bg-sre-surface/30 rounded-xl p-6 border border-sre-border/50">
        <h3 className="text-lg font-semibold text-sre-text mb-4 flex items-center gap-2">
          <span className="material-icons text-sre-primary">info</span>
          Basic Information
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="block text-sm font-medium text-sre-text">
              Channel Name{" "}
              <HelpTooltip text="Enter a descriptive name for this notification channel." />
            </label>
            <Input
              value={formData.name}
              onChange={(e) =>
                setFormData({ ...formData, name: e.target.value })
              }
              required
              placeholder="Team Slack Channel"
              className="bg-sre-bg border-sre-border/60 focus:border-sre-primary"
            />
          </div>

          <div className="space-y-2">
            <label className="block text-sm font-medium text-sre-text">
              Channel Type{" "}
              <HelpTooltip text="Select the type of notification service you want to integrate with." />
            </label>
            <Select
              value={formData.type}
              onChange={(e) =>
                setFormData({ ...formData, type: e.target.value, config: {} })
              }
              className="bg-sre-bg border-sre-border/60 focus:border-sre-primary"
            >
              {channelTypeOptions.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </Select>
            {channelTypeOptions.length === 0 && (
              <p className="text-xs text-sre-text-muted mt-2">
                No channel types are enabled by organization policy.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Channel Type Preview */}
      {formData.type && (
        <div className="bg-gradient-to-r from-sre-primary/5 to-sre-accent/5 rounded-xl p-6 border border-sre-primary/20">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-12 h-12 rounded-xl bg-sre-primary/10 flex items-center justify-center">
              <span className="material-icons text-2xl text-sre-primary">
                {channelTypeOptions.find((opt) => opt.value === formData.type)
                  ?.icon || "notifications"}
              </span>
            </div>
            <div>
              <h4 className="text-lg font-semibold text-sre-text">
                {
                  channelTypeOptions.find((opt) => opt.value === formData.type)
                    ?.label
                }
              </h4>
              <p className="text-sm text-sre-text-muted">
                {
                  channelTypeOptions.find((opt) => opt.value === formData.type)
                    ?.description
                }
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Configuration Section */}
      {renderConfigFields() && (
        <div className="bg-sre-surface/30 rounded-xl p-6 border border-sre-border/50">
          <h3 className="text-lg font-semibold text-sre-text mb-4 flex items-center gap-2">
            <span className="material-icons text-sre-primary">settings</span>
            Configuration
          </h3>
          <div className="space-y-4">{renderConfigFields()}</div>
        </div>
      )}

      {/* Settings Section */}
      <div className="bg-sre-surface/30 rounded-xl p-6 border border-sre-border/50">
        <h3 className="text-lg font-semibold text-sre-text mb-4 flex items-center gap-2">
          <span className="material-icons text-sre-primary">tune</span>
          Settings
        </h3>

        <div className="space-y-4">
          <label className="flex items-center gap-3 p-3 bg-sre-bg/50 rounded-lg border border-sre-border/30 hover:border-sre-primary/30 transition-colors cursor-pointer">
            <input
              type="checkbox"
              id="channel-enabled"
              checked={formData.enabled}
              onChange={(e) =>
                setFormData({ ...formData, enabled: e.target.checked })
              }
              className="w-5 h-5 text-sre-primary border-sre-border rounded focus:ring-sre-primary focus:ring-2"
            />
            <div className="flex-1">
              <div className="font-medium text-sre-text">
                Enable this channel
              </div>
              <div className="text-sm text-sre-text-muted">
                Only enabled channels will receive alert notifications
              </div>
            </div>
            <HelpTooltip text="Only enabled channels will receive alert notifications." />
          </label>
        </div>
      </div>

      {/* Group sharing when in the 'group' tab — visibility itself is set by the Integrations page tab */}
      {formData.visibility === "group" && groups?.length > 0 && (
        <div className="bg-sre-surface/30 rounded-xl p-6 border border-sre-border/50">
          <h3 className="text-lg font-semibold text-sre-text mb-4 flex items-center gap-2">
            <span className="material-icons text-sre-primary">group</span>
            Group Sharing
          </h3>

          <div className="space-y-3">
            <div className="text-sm text-sre-text-muted mb-3">
              Select which user groups can view and edit this notification
              channel.
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-64 overflow-y-auto p-3 border border-sre-border/30 rounded-lg bg-sre-bg/30">
              {groups.map((group) => (
                <label
                  key={group.id}
                  className={`flex items-center gap-3 p-3 rounded-lg border transition-all cursor-pointer ${
                    selectedGroups.has(group.id)
                      ? "bg-sre-primary/10 border-sre-primary/30 text-sre-primary"
                      : "bg-sre-surface/50 border-sre-border/20 hover:border-sre-primary/20 hover:bg-sre-primary/5"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selectedGroups.has(group.id)}
                    onChange={() => toggleGroup(group.id)}
                    className="w-4 h-4 text-sre-primary border-sre-border rounded focus:ring-sre-primary focus:ring-2"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sre-text truncate">
                      {group.name}
                    </div>
                    {group.description && (
                      <div className="text-xs text-sre-text-muted truncate">
                        {group.description}
                      </div>
                    )}
                  </div>
                </label>
              ))}
            </div>

            <div className="text-xs text-sre-text-muted">
              {selectedGroups.size} group{selectedGroups.size === 1 ? "" : "s"}{" "}
              selected
            </div>
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex justify-end gap-3 pt-4 border-t border-sre-border/50">
        <Button
          type="button"
          variant="ghost"
          onClick={onCancel}
          className="px-6 py-2"
        >
          Cancel
        </Button>
        <Button
          type="submit"
          className="px-6 py-2 bg-sre-primary hover:bg-sre-primary-light text-white shadow-lg hover:shadow-xl transition-all"
        >
          <span className="material-icons text-sm mr-2">save</span>
          Save Channel
        </Button>
      </div>
    </form>
  );
}

ChannelEditor.propTypes = {
  channel: PropTypes.shape({
    name: PropTypes.string,
    type: PropTypes.string,
    enabled: PropTypes.bool,
    config: PropTypes.object,
    sharedGroupIds: PropTypes.arrayOf(PropTypes.string),
  }),
  onSave: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
  allowedTypes: PropTypes.arrayOf(PropTypes.string),
  // the Integrations page tab controls visibility (private|group|tenant)
  visibility: PropTypes.oneOf(["private", "group", "tenant"]),
};
