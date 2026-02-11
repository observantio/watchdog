/**
 * UI Component Library
 * Reusable UI components with SRE-themed styling
 */
import React from 'react'
import { createPortal } from 'react-dom'
import PropTypes from 'prop-types'
import clsx from 'clsx'

/**
 * Button component with SRE styling
 * @param {object} props - Component props
 * @param {React.ReactNode} props.children - Button content
 * @param {'primary'|'secondary'|'success'|'danger'|'ghost'} props.variant - Button variant
 * @param {'sm'|'md'|'lg'} props.size - Button size
 * @param {boolean} props.loading - Loading state
 * @param {string} props.className - Additional CSS classes
 */
export function Button({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  className,
  ...props
}) {
  const baseClasses = 'inline-flex items-center justify-center font-medium rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-sre-bg'
  
  const variants = {
    primary: 'bg-sre-primary hover:bg-sre-primary-light text-white shadow-glow-sm hover:shadow-glow focus:ring-sre-primary',
    secondary: 'bg-sre-surface hover:bg-sre-surface-light text-sre-text border border-sre-border focus:ring-sre-surface',
    success: 'bg-sre-success hover:bg-sre-success-light text-white focus:ring-sre-success',
    danger: 'bg-sre-error hover:bg-sre-error-light text-white focus:ring-sre-error',
    ghost: 'text-sre-text-muted hover:text-sre-text hover:bg-sre-surface/50 focus:ring-sre-surface',
  }
  
  const sizes = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-base',
    lg: 'px-6 py-3 text-lg',
  }
  
  return (
    <button
      className={clsx(baseClasses, variants[variant], sizes[size], className)}
      disabled={loading}
      {...props}
    >
      {loading && (
        <svg className="animate-spin -ml-1 mr-2 h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      )}
      {children}
    </button>
  )
}

Button.propTypes = {
  children: PropTypes.node.isRequired,
  variant: PropTypes.oneOf(['primary', 'secondary', 'success', 'danger', 'ghost']),
  size: PropTypes.oneOf(['sm', 'md', 'lg']),
  loading: PropTypes.bool,
  className: PropTypes.string,
}

/**
 * Card component for content sections
 * @param {object} props - Component props
 * @param {React.ReactNode} props.children - Card content
 * @param {string} props.className - Additional CSS classes
 * @param {string} props.title - Card title
 * @param {string} props.subtitle - Card subtitle
 * @param {React.ReactNode} props.action - Card action element
 */
export function Card({ children, className, title, subtitle, action, ...props }) {
  const isInteractive = props.draggable || props.onClick || props.onDragStart || props.onDragOver || props.onDrop || props.onDragEnd
  const Component = isInteractive ? 'button' : 'div'
  return (
    <Component
      className={clsx(
        'bg-sre-surface/50 rounded-xl',
        'transition-all duration-300',
        'hover:border-sre-border/80',
        className
      )}
      {...(isInteractive ? { type: 'button' } : {})}
      {...props}
    >
      {(title || action) && (
        <div className="flex items-start justify-between mb-4">
          <div>
            {title && <h3 className="text-lg font-semibold text-sre-text text-left">{title}</h3>}
            {subtitle && <p className="text-sm text-sre-text-muted mt-1 text-left">{subtitle}</p>}
          </div>
          {action && <div>{action}</div>}
        </div>
      )}
      {children}
    </Component>
  )
}

Card.propTypes = {
  children: PropTypes.node.isRequired,
  className: PropTypes.string,
  title: PropTypes.string,
  subtitle: PropTypes.string,
  action: PropTypes.node,
}

/**
 * Card subcomponents for composition
 */
export function CardHeader({ children, className, ...props }) {
  return (
    <div className={clsx('px-6 py-4 border-b border-sre-border/30', className)} {...props}>
      {children}
    </div>
  )
}

export function CardContent({ children, className, ...props }) {
  return (
    <div className={clsx('px-6 py-4', className)} {...props}>
      {children}
    </div>
  )
}

export function CardTitle({ children, className, ...props }) {
  return (
    <h3 className={clsx('text-lg font-semibold text-sre-text', className)} {...props}>{children}</h3>
  )
}

CardHeader.propTypes = {
  children: PropTypes.node,
  className: PropTypes.string,
}

CardContent.propTypes = {
  children: PropTypes.node,
  className: PropTypes.string,
}

CardTitle.propTypes = {
  children: PropTypes.node,
  className: PropTypes.string,
}

/**
 * Badge component for status indicators
 * @param {object} props - Component props
 * @param {React.ReactNode} props.children - Badge content
 * @param {'default'|'success'|'warning'|'error'|'info'|'neon'} props.variant - Badge variant
 * @param {string} props.className - Additional CSS classes
 */
export function Badge({ children, variant = 'default', className, ...props }) {
    const variants = {
        default: 'bg-sre-surface-light text-sre-text border-sre-border',
        success: 'bg-sre-success/10 text-sre-success border-sre-success/20',
        warning: 'bg-sre-warning/10 text-sre-warning border-sre-warning/20',
        error: 'bg-sre-error/10 text-sre-error border-sre-error/20',
        info: 'bg-sre-primary/10 text-sre-primary border-sre-primary/20',
        neon: 'bg-sre-neon/10 text-sre-neon border-sre-neon/20 glow',
    }
    
    return (
        <span
            className={clsx(
                'inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border w-max text-center',
                variants[variant],
                className
            )}
            {...props}
        >
            {children}
        </span>
    )
}

Badge.propTypes = {
  children: PropTypes.node.isRequired,
  variant: PropTypes.oneOf(['default', 'success', 'warning', 'error', 'info', 'neon']),
  className: PropTypes.string,
}

/**
 * Input component with SRE styling
 */
export function Input({ label, error, helperText, className, ...props }) {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-sre-text mb-2">
          {label}
        </label>
      )}
      <input
        className={clsx(
          'w-full px-3 py-1.5 bg-sre-surface border border-sre-border rounded-lg',
          'text-sre-text placeholder-sre-text-subtle',
          'focus:outline-none focus:ring-2 focus:ring-sre-primary focus:border-transparent',
          'transition-all duration-200',
          error && 'border-sre-error focus:ring-sre-error',
          className
        )}
        {...props}
      />
      {error && (
        <p className="mt-1 text-sm text-sre-error">{error}</p>
      )}
      {helperText && !error && (
        <p className="mt-1 text-sm text-sre-text-muted">{helperText}</p>
      )}
    </div>
  )
}

Input.propTypes = {
  label: PropTypes.string,
  error: PropTypes.string,
  helperText: PropTypes.string,
  className: PropTypes.string,
}

/**
 * Select component with SRE styling
 */
export function Select({ label, error, helperText, children, className, ...props }) {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-sre-text mb-2">
          {label}
        </label>
      )}
      <select
        className={clsx(
          'w-full px-4 pr-10 py-2 bg-sre-surface border border-sre-border rounded-lg',
          'text-sre-text',
          'focus:outline-none focus:ring-2 focus:ring-sre-primary focus:border-transparent',
          'transition-all duration-200 cursor-pointer',
          error && 'border-sre-error focus:ring-sre-error',
          className
        )}
        {...props}
      >
        {children}
      </select>
      {error && (
        <p className="mt-1 text-sm text-sre-error">{error}</p>
      )}
      {helperText && !error && (
        <p className="mt-1 text-sm text-sre-text-muted">{helperText}</p>
      )}
    </div>
  )
}

Select.propTypes = {
  label: PropTypes.string,
  error: PropTypes.string,
  helperText: PropTypes.string,
  children: PropTypes.node.isRequired,
  className: PropTypes.string,
}

/**
 * Metric display component
 */
export function MetricCard({ label, value, trend, status, icon, className }) {
  const statusColors = {
    success: 'text-sre-success',
    warning: 'text-sre-warning',
    error: 'text-sre-error',
    info: 'text-sre-primary',
    default: 'text-sre-text',
  }
  
  return (
    <div
      className={clsx(
        'bg-gradient-to-br from-sre-surface to-sre-surface/80 border-2 border-sre-border/50',
        'hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm',
        'rounded-lg p-4 relative overflow-visible',
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-sm text-sre-text-muted mb-1">{label}</p>
          <div className={clsx(
            'text-2xl font-mono font-bold',
            status ? statusColors[status] : 'text-sre-text'
          )}>
            {value}
          </div>
          {trend && (
            <p className="text-xs text-sre-text-subtle mt-1">{trend}</p>
          )}
        </div>
        {icon && (
          <div className="ml-3 text-sre-text-muted">
            {icon}
          </div>
        )}
      </div>
    </div>
  )
}

MetricCard.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.node.isRequired,
  trend: PropTypes.string,
  status: PropTypes.oneOf(['success', 'warning', 'error', 'info', 'default']),
  icon: PropTypes.node,
  className: PropTypes.string,
}

/**
 * Code block component with syntax highlighting
 */
export function CodeBlock({ children, language = 'json', className }) {
  return (
    <pre
      className={clsx(
        'bg-sre-bg-alt border border-sre-border rounded-lg p-4',
        'text-sm font-mono text-sre-text-muted overflow-x-auto',
        'scrollbar-thin scrollbar-thumb-sre-border scrollbar-track-transparent',
        className
      )}
    >
      <code className={`language-${language}`}>{children}</code>
    </pre>
  )
}

CodeBlock.propTypes = {
  children: PropTypes.node.isRequired,
  language: PropTypes.string,
  className: PropTypes.string,
}

/**
 * Alert/Notification component
 */
export function Alert({ children, variant = 'info', title, onClose, className }) {
  const variants = {
    info: 'bg-sre-primary/10 border-sre-primary/30 text-sre-primary',
    success: 'bg-sre-success/10 border-sre-success/30 text-sre-success',
    warning: 'bg-sre-warning/10 border-sre-warning/30 text-sre-warning',
    error: 'bg-sre-error/10 border-sre-error/30 text-sre-error',
  }
  
  return (
    <div
      className={clsx(
        'rounded-lg border p-4 animate-slide-up',
        variants[variant],
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          {title && <h4 className="font-semibold mb-1">{title}</h4>}
          <div className="text-sm">{children}</div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="ml-3 text-current hover:opacity-70 transition-opacity"
          >
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}

Alert.propTypes = {
  children: PropTypes.node.isRequired,
  variant: PropTypes.oneOf(['info', 'success', 'warning', 'error']),
  title: PropTypes.string,
  onClose: PropTypes.func,
  className: PropTypes.string,
}

/**
 * Small helper to render descriptive text inside an Alert
 */
export function AlertDescription({ children, className, ...props }) {
  return (
    <div className={clsx('text-sm text-sre-text-muted', className)} {...props}>
      {children}
    </div>
  )
}

AlertDescription.propTypes = {
  children: PropTypes.node.isRequired,
  className: PropTypes.string,
}

/**
 * Loading spinner component
 */
export function Spinner({ size = 'md', className }) {
  const sizes = {
    sm: 'w-4 h-4',
    md: 'w-8 h-8',
    lg: 'w-12 h-12',
  }
  
  return (
    <div className={clsx('flex items-center justify-center', className)}>
      <svg
        className={clsx('animate-spin text-sre-primary', sizes[size])}
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
    </div>
  )
}

Spinner.propTypes = {
  size: PropTypes.oneOf(['sm', 'md', 'lg']),
  className: PropTypes.string,
}

/**
 * Simple sparkline chart using SVG
 */
export function Sparkline({ data = [], width = 200, height = 40, stroke = 'currentColor', strokeWidth = 2, fill = 'none', className }) {
  if (!data?.length) {
    return (
      <div className={clsx('flex items-center justify-center text-xs text-sre-text-muted', className)} style={{width, height}}>
        no data
      </div>
    )
  }

  const values = data
    .map(d => (typeof d === 'number' ? d : (d?.[1] ?? d)))
    .map(Number)
    .filter(v => Number.isFinite(v))

  if (!values.length) {
    return (
      <div className={clsx('flex items-center justify-center text-xs text-sre-text-muted', className)} style={{width, height}}>
        no data
      </div>
    )
  }

  const safeValues = values.length === 1 ? [values[0], values[0]] : values
  const min = Math.min(...safeValues)
  const max = Math.max(...safeValues)
  const range = max - min || 1

  const points = safeValues.map((v, i) => {
    const denom = safeValues.length > 1 ? (safeValues.length - 1) : 1
    const x = (i / denom) * width
    const y = height - ((v - min) / range) * height
    return `${x},${y}`
  }).join(' ')

  const areaPoints = fill === 'none' ? points : `0,${height} ${points} ${width},${height}`

  return (
    <svg width={width} height={height} className={className} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      {fill !== 'none' && (
        <polygon
          fill={fill}
          points={areaPoints}
          opacity="0.3"
        />
      )}
      <polyline
        fill="none"
        stroke={stroke}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  )
}

Sparkline.propTypes = {
  data: PropTypes.arrayOf(PropTypes.oneOfType([PropTypes.number, PropTypes.array])),
  width: PropTypes.number,
  height: PropTypes.number,
  stroke: PropTypes.string,
  strokeWidth: PropTypes.number,
  fill: PropTypes.string,
  className: PropTypes.string,
}

/**
 * Modal component for dialogs and overlays
 */
export function Modal({ 
  isOpen, 
  onClose, 
  title, 
  children, 
  footer,
  size = 'md',
  showCloseButton = true,
  closeOnOverlayClick = true,
  className
}) {
  const sizes = {
    sm: 'max-w-md',
    md: 'max-w-2xl',
    lg: 'max-w-4xl',
    xl: 'max-w-6xl',
    full: 'max-w-[95vw]',
  }

  const handleOverlayClick = (e) => {
    if (closeOnOverlayClick && e.target === e.currentTarget) {
      onClose?.()
    }
  }

  const contentRef = React.useRef(null)
  // keep a ref to the latest onClose to avoid re-running the effect
  // on every render when parent re-creates the onClose callback.
  const onCloseRef = React.useRef(onClose)
  React.useEffect(() => { onCloseRef.current = onClose }, [onClose])

  React.useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape') {
        onCloseRef.current?.()
      }
    }

    const prevBodyOverflow = document.body.style.overflow
    const prevHtmlOverflow = document.documentElement.style.overflow

    if (isOpen) {
      document.addEventListener('keydown', handleEscape)
      document.body.style.overflow = 'hidden'
      document.documentElement.style.overflow = 'hidden'
      // focus modal content to avoid focus landing on backdrop
      setTimeout(() => {
        try {
          contentRef.current?.focus({ preventScroll: true })
        } catch (e) {
          console.warn("Failed to focus modal content:", e)
          contentRef.current?.focus()
        }
      }, 0)
    }

    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = prevBodyOverflow
      document.documentElement.style.overflow = prevHtmlOverflow
    }
  }, [isOpen])

  if (!isOpen) return null

  const content = (
    <div
      className="fixed inset-0 flex items-center justify-center p-4 animate-fade-in bg-transparent overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? "modal-title" : undefined}
      onClick={handleOverlayClick}
      style={{ zIndex: 9999 }}
    >
      <div 
        className={clsx(
          'relative bg-sre-bg-card rounded-xl shadow-2xl w-full mx-auto',
          'border border-sre-border/50',
          'animate-slide-up',
          'flex flex-col',
          sizes[size],
          className
        )}
        style={{ zIndex: 10000, maxHeight: 'calc(100vh - 4rem)' }}
        ref={contentRef}
        tabIndex={-1}
      >
        {/* Header */}
        {(title || showCloseButton) && (
          <div className="flex items-center justify-between px-6 py-4 border-sre-border">
            <h2 id="modal-title" className="text-xl font-bold text-sre-text">{title}</h2>
            {showCloseButton && (
              <button
                onClick={onClose}
                className="text-sre-text-muted hover:text-sre-text transition-colors p-1 rounded-lg hover:bg-sre-surface/50"
                aria-label="Close modal"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        )}

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 scrollbar-thin scrollbar-thumb-sre-border scrollbar-track-transparent">
          {children}
        </div>

        {/* Footer */}
        {footer && (
          <div className="px-6 py-4 border-sre-border bg-sre-surface/30">
            {footer}
          </div>
        )}
      </div>
    </div>
  )

  return createPortal(content, document.body)
}

Modal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  title: PropTypes.string,
  children: PropTypes.node.isRequired,
  footer: PropTypes.node,
  size: PropTypes.oneOf(['sm', 'md', 'lg', 'xl', 'full']),
  showCloseButton: PropTypes.bool,
  closeOnOverlayClick: PropTypes.bool,
  className: PropTypes.string,
}

/**
 * Confirmation Dialog component
 */
export function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title = 'Confirm Action',
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'danger',
  loading = false,
}) {
  const handleConfirm = async () => {
    await onConfirm?.()
    onClose?.()
  }

  return (
    <Modal 
      isOpen={isOpen} 
      onClose={onClose} 
      title={title}
      size="sm"
      closeOnOverlayClick={!loading}
      footer={
        <div className="flex gap-3 justify-end">
          <Button
            variant="ghost"
            onClick={onClose}
            disabled={loading}
          >
            {cancelText}
          </Button>
          <Button
            variant={variant}
            onClick={handleConfirm}
            loading={loading}
            disabled={loading}
          >
            {confirmText}
          </Button>
        </div>
      }
    >
      <div className="py-4">
        <p className="text-sre-text">{message}</p>
      </div>
    </Modal>
  )
}

ConfirmDialog.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  onConfirm: PropTypes.func.isRequired,
  title: PropTypes.string,
  message: PropTypes.string.isRequired,
  confirmText: PropTypes.string,
  cancelText: PropTypes.string,
  variant: PropTypes.oneOf(['primary', 'secondary', 'success', 'danger', 'ghost']),
  loading: PropTypes.bool,
}

/**
 * Textarea component with SRE styling
 */
export function Textarea({ label, error, helperText, className, rows = 4, ...props }) {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-sre-text mb-2">
          {label}
        </label>
      )}
      <textarea
        rows={rows}
        className={clsx(
          'w-full px-4 py-2 bg-sre-surface border border-sre-border rounded-lg',
          'text-sre-text placeholder-sre-text-subtle',
          'focus:outline-none focus:ring-2 focus:ring-sre-primary focus:border-transparent',
          'transition-all duration-200 resize-vertical',
          error && 'border-sre-error focus:ring-sre-error',
          className
        )}
        {...props}
      />
      {error && (
        <p className="mt-1 text-sm text-sre-error">{error}</p>
      )}
      {helperText && !error && (
        <p className="mt-1 text-sm text-sre-text-muted">{helperText}</p>
      )}
    </div>
  )
}

Textarea.propTypes = {
  label: PropTypes.string,
  error: PropTypes.string,
  helperText: PropTypes.string,
  className: PropTypes.string,
  rows: PropTypes.number,
}

/**
 * Checkbox component with SRE styling
 */
export function Checkbox({ label, error, helperText, className, ...props }) {
  return (
    <div >
      <div className="flex mt-1 gap-2">
        <input
          type="checkbox"
          className={clsx(
            'w-4 h-4 rounded border-sre-border bg-sre-surface',
            'text-sre-primary focus:ring-2 focus:ring-sre-primary focus:ring-offset-0',
            'transition-all duration-200 cursor-pointer',
            error && 'border-sre-error',
            className
          )}
          {...props}
        />
        {label && (
          <label className="text-sm text-sre-text cursor-pointer select-none">
            {label}
          </label>
        )}
      </div>
      {error && (
        <p className="mt-1 text-sm text-sre-error">{error}</p>
      )}
      {helperText && !error && (
        <p className="mt-1 text-sm text-sre-text-muted">{helperText}</p>
      )}
    </div>
  )
}

Checkbox.propTypes = {
  label: PropTypes.string,
  error: PropTypes.string,
  helperText: PropTypes.string,
  className: PropTypes.string,
}

