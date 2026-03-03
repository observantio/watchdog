import { useEffect, useRef, useState } from "react";
import PropTypes from "prop-types";
import { Button } from "./ui";

export default function ConfirmModal({
  isOpen,
  title,
  message,
  onConfirm,
  onCancel,
  confirmText = "Confirm",
  cancelText = "Cancel",
  variant = "danger",
}) {
  const modalRef = useRef(null);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (isOpen) {
      modalRef.current?.focus();
      setConfirming(false);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === "Escape" && isOpen && !confirming) {
        onCancel();
      }
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [confirming, isOpen, onCancel]);

  const safeCancel = (e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (confirming) return;
    onCancel();
  };

  const safeConfirm = async (e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (confirming) return;
    setConfirming(true);
    try {
      await onConfirm();
    } finally {
      setConfirming(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in"
      onMouseDown={safeCancel}
      onClick={safeCancel}
      role="button"
      tabIndex="-1"
    >
      <div
        ref={modalRef}
        className="bg-sre-bg border border-sre-border rounded-lg shadow-2xl w-full max-w-md animate-slide-up"
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="modal-title"
        aria-describedby="modal-message"
        tabIndex={-1}
      >
        <div className="p-6">
          <h3 id="modal-title" className="text-xl font-bold text-sre-text mb-4">
            {title}
          </h3>
          <p id="modal-message" className="text-sre-text-muted mb-6">
            {message}
          </p>
          <div className="flex gap-3 justify-end">
            <Button type="button" onClick={safeCancel} variant="ghost" size="md" disabled={confirming}>
              {cancelText}
            </Button>
            <Button type="button" onClick={safeConfirm} variant={variant} size="md" loading={confirming}>
              {confirmText}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

ConfirmModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  title: PropTypes.string.isRequired,
  message: PropTypes.string.isRequired,
  onConfirm: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
  confirmText: PropTypes.string,
  cancelText: PropTypes.string,
  variant: PropTypes.oneOf(["danger", "primary", "success"]),
};
