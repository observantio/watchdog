import { useEffect, useRef } from 'react'
import PropTypes from 'prop-types'
import { Button } from './ui'

export default function ConfirmModal({
  isOpen,
  title,
  message,
  onConfirm,
  onCancel,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'danger'
}) {
  const modalRef = useRef(null)

  useEffect(() => {
    if (isOpen) {
      modalRef.current?.focus()
    }
  }, [isOpen])

  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onCancel()
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [isOpen, onCancel])

  if (!isOpen) return null

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 animate-fade-in"
      onClick={onCancel}
      role="button"
      tabIndex="-1"
    >
      <div
        ref={modalRef}
        className="bg-sre-bg border border-sre-border rounded-lg shadow-2xl w-full max-w-md animate-slide-up"
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
            <Button onClick={onCancel} variant="ghost" size="md">
              {cancelText}
            </Button>
            <Button onClick={onConfirm} variant={variant} size="md">
              {confirmText}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

ConfirmModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  title: PropTypes.string.isRequired,
  message: PropTypes.string.isRequired,
  onConfirm: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
  confirmText: PropTypes.string,
  cancelText: PropTypes.string,
  variant: PropTypes.oneOf(['danger', 'primary', 'success'])
}
