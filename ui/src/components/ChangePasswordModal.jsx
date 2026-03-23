import { useState } from "react";
import PropTypes from "prop-types";
import { Modal, Button } from "./ui";
import { useToast } from "../contexts/ToastContext";
import HelpTooltip from "./HelpTooltip";
import * as api from "../api";

export default function ChangePasswordModal({
  isOpen,
  onClose,
  userId,
  authProvider = "local",
  isForced = false,
}) {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [showTour, setShowTour] = useState(false);
  const [slideIndex, setSlideIndex] = useState(0);
  const [formData, setFormData] = useState({
    currentPassword: "",
    newPassword: "",
    confirmPassword: "",
  });
  const [showPassword, setShowPassword] = useState({
    current: false,
    next: false,
    confirm: false,
  });

  const slides = [
    {
      title: "A Gentle Observatory",
      body: "In a world of money-driven monitoring tools, I wanted to create something that puts users first. Watchdog is designed to be simple, transparent, and user-friendly. Using open source components and a clean interface, it gives you powerful observability without the complexity and cost of traditional platforms.",
    },
    {
      title: "Traces — Threads of Time",
      body: "With Tempo, we got distributed tracing right at the core. It’s built to handle high volumes of trace data with ease, giving you deep insights into your applications without breaking the bank.",
    },
    {
      title: "Logs — Stories in Motion",
      body: "You don’t need to be a logging expert to get value from your logs. With Loki, you can easily search and explore your logs alongside your traces and metrics, all in one place.",
    },
    {
      title: "Alerts — Quiet Guardians",
      body: "With Notifier built on top of Alertmanager, you can set up powerful alerting rules and notifications to stay on top of your system’s health. It’s flexible, reliable, and integrates seamlessly with the rest of the platform. It can ingest alerts from any source, so you can centralize your alerting and never miss a critical issue again.",
    },
    {
      title: "Dashboards — Windows of Truth",
      body: "What about dashboards? Watchdog has you covered there too. With Grafana, you can create beautiful, customizable dashboards to visualize your data and share insights with your team.",
    },
    {
      title: "RCA — Root Cause Analysis",
      body: "With Resolver you can easily identify and resolve issues quickly. Our integrated root cause analysis tools help you understand the underlying causes of problems, so you can fix them faster and prevent future occurrences. It is runs AI powered RCA on your traces and logs, giving you actionable insights to resolve incidents faster than ever before.",
    },
    {
      title: "Teams — Shared Stewardship",
      body: "We thought about teams too. With robust user management and role-based access control, you can easily manage permissions and keep your data secure. Scope dashboards, channels to specific teams or projects, and ensure everyone has the right level of access.",
    },
    {
      title: "Open Source — Freedom to Observe",
      body: "Best of all, Watchdog is open source and self-hosted, giving you full control over your data and your monitoring. No vendor lock-in, no hidden costs, just a powerful observability platform that puts you in the driver’s seat. You will only be running to costs to run these servers. Support us by starring the project on GitHub and sharing it with your friends and colleagues.  Let’s build a better monitoring future together!",
    },
  ];

  const canSkipCurrentPassword = isForced && authProvider !== "local";

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (formData.newPassword.length < 12) {
      toast.error("Password must be at least 12 characters long");
      return;
    }

    if (formData.newPassword !== formData.confirmPassword) {
      toast.error("New passwords do not match");
      return;
    }

    setLoading(true);
    try {
      await api.updateUserPassword(userId, {
        current_password: canSkipCurrentPassword ? null : formData.currentPassword,
        new_password: formData.newPassword,
      });
      toast.success("Password updated successfully");
      setFormData({
        currentPassword: "",
        newPassword: "",
        confirmPassword: "",
      });
      if (isForced) {
        setShowTour(true);
        setSlideIndex(0);
      } else {
        onClose();
      }
    } catch (err) {
      toast.error(
        err?.body?.detail || err?.message || "Password update failed",
      );
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (field, value) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const renderPasswordField = ({
    id,
    fieldKey,
    label,
    placeholder,
    value,
    onChange,
    helpText,
    required = true,
    minLength = undefined,
    autoFocus = false,
  }) => (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <label htmlFor={id} className="text-sm font-medium text-sre-text">
          {label}
        </label>
        <HelpTooltip text={helpText} showOnFocus={false} />
      </div>
      <div className="relative">
        <span className="material-icons pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sre-text-muted text-[18px]">
          lock
        </span>
        <input
          id={id}
          type={showPassword[fieldKey] ? "text" : "password"}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          required={required}
          minLength={minLength}
          autoFocus={autoFocus}
          className="w-full rounded-lg border border-sre-border bg-sre-surface py-2 pl-10 pr-10 text-sre-text placeholder-sre-text-subtle focus:outline-none focus:ring-2 focus:ring-sre-primary focus:border-transparent transition-all duration-200"
        />
        <button
          type="button"
          onClick={() =>
            setShowPassword((prev) => ({ ...prev, [fieldKey]: !prev[fieldKey] }))
          }
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-sre-text-muted hover:text-sre-text hover:bg-sre-surface-light transition-colors"
          aria-label={showPassword[fieldKey] ? "Hide password" : "Show password"}
          title={showPassword[fieldKey] ? "Hide password" : "Show password"}
        >
          <span className="material-icons text-[18px]">
            {showPassword[fieldKey] ? "visibility_off" : "visibility"}
          </span>
        </button>
      </div>
    </div>
  );

  let modalTitle;
  if (showTour) {
    modalTitle = slides[slideIndex]?.title || "Welcome to Watchdog";
  } else if (isForced) {
    modalTitle = "Password Change Required";
  } else {
    modalTitle = "Change Password";
  }

  let modalOnClose;
  if (isForced && showTour) {
    modalOnClose = undefined;
  } else if (isForced) {
    modalOnClose = undefined;
  } else {
    modalOnClose = onClose;
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={modalOnClose}
      title={modalTitle}
      size="md"
      closeOnOverlayClick={false}
      showCloseButton={!!modalOnClose}
      className="bg-sre-bg-card rounded-xl shadow-2xl p-4 w-full mx-auto border border-sre-border/50 animate-slide-up flex flex-col max-w-2xl"
    >
      {!showTour && (
        <div
          className={`mb-4 rounded-lg border p-3 text-sm ${
            isForced
              ? "border-yellow-500/60 bg-yellow-500/10 text-yellow-500"
              : "border-sre-primary/30 bg-sre-primary/10 text-sre-text"
          }`}
        >
          <div className="flex items-start gap-2">
            <span className="material-icons text-base leading-none mt-0.5">
              {isForced ? "warning" : "lock_person"}
            </span>
            <div>
              <div className="font-semibold">
                {isForced ? "Password change required" : "Password security"}
              </div>
              <div className={isForced ? "text-yellow-500/90" : "text-sre-text-muted"}>
                {isForced
                  ? "You must change your password before continuing. Please choose a secure password with at least 12 characters."
                  : "Use a strong password with at least 12 characters, and avoid reusing passwords across services."}
              </div>
            </div>
          </div>
        </div>
      )}
      {showTour ? (
        <div className="space-y-4">
          <div className="">
            {(() => {
              const slide = slides[slideIndex] || {};
              return (
                <div>
                  <div className="text-sm text-sre-text-muted">
                    {slide.body}
                  </div>
                </div>
              );
            })()}
          </div>

          <div className="flex items-center justify-between">
            <div className="text-xs text-sre-text-muted">
              {slideIndex + 1} / {slides.length}
            </div>
            <div className="flex gap-2">
              <Button
                variant="ghost"
                onClick={() => setSlideIndex((i) => Math.max(0, i - 1))}
                disabled={slideIndex === 0}
              >
                Prev
              </Button>
              {slideIndex < slides.length - 1 ? (
                <Button
                  variant="primary"
                  onClick={() =>
                    setSlideIndex((i) => Math.min(slides.length - 1, i + 1))
                  }
                >
                  Next
                </Button>
              ) : (
                <Button
                  variant="primary"
                  onClick={() => {
                    setShowTour(false);
                    if (onClose) onClose();
                  }}
                >
                  Done
                </Button>
              )}
            </div>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          {!canSkipCurrentPassword && (
            renderPasswordField({
              id: "currentPassword",
              fieldKey: "current",
              label: "Current Password",
              placeholder: "Enter current password",
              value: formData.currentPassword,
              onChange: (e) => handleChange("currentPassword", e.target.value),
              helpText:
                "Enter your current password to verify your identity before changing it.",
              autoFocus: true,
            })
          )}

          {renderPasswordField({
            id: "newPassword",
            fieldKey: "next",
            label: "New Password",
            placeholder: "Enter new password (min 12 characters)",
            value: formData.newPassword,
            onChange: (e) => handleChange("newPassword", e.target.value),
            helpText:
              "Choose a strong password with at least 12 characters, including uppercase, lowercase, numbers, and special characters.",
            minLength: 12,
          })}

          {renderPasswordField({
            id: "confirmPassword",
            fieldKey: "confirm",
            label: "Confirm New Password",
            placeholder: "Confirm new password",
            value: formData.confirmPassword,
            onChange: (e) => handleChange("confirmPassword", e.target.value),
            helpText: "Re-enter your new password to ensure it matches exactly.",
            minLength: 12,
          })}

          <div className="flex gap-3 justify-end pt-4">
            {!isForced && (
              <Button onClick={onClose} variant="ghost" disabled={loading}>
                Cancel
              </Button>
            )}
            <Button type="submit" variant="primary" loading={loading}>
              {loading ? "Updating..." : "Update Password"}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}

ChangePasswordModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  userId: PropTypes.string.isRequired,
  authProvider: PropTypes.string,
  isForced: PropTypes.bool,
};
