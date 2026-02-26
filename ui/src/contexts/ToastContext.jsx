import { createContext, useContext, useState, useCallback, useEffect, useMemo, useRef } from 'react';
import PropTypes from 'prop-types';
import { setSetupToken } from '../api'

const ToastContext = createContext();

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return context;
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const recentErrorsRef = useRef(new Map());
  const toastTimersRef = useRef(new Map());

  const removeToast = useCallback((id) => {
    const timer = toastTimersRef.current.get(id)
    if (timer) {
      clearTimeout(timer)
      toastTimersRef.current.delete(id)
    }
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const formatMessage = (m) => {
    if (m == null) return ''
    if (typeof m === 'string') return m
    if (typeof m === 'number' || typeof m === 'boolean') return String(m)
    if (m instanceof Error) return m.message || String(m)
    if (typeof m === 'object') {
      if (Array.isArray(m.detail) && m.detail.length > 0) {
        try {
          const parts = m.detail.map(d => {
            const msg = d.msg || d.message || JSON.stringify(d)
            const loc = Array.isArray(d.loc) ? d.loc.join('.') : (d.loc ? String(d.loc) : '')
            return loc ? `${msg} at ${loc}` : msg
          })
          return parts.join('; ')
        } catch (ex) {
          // fallthrough to JSON stringify
        }
      }
      if (typeof m.detail === 'string') return m.detail
      if (Array.isArray(m.errors) && m.errors.length) return m.errors.join('; ')
      if (typeof m.errors === 'string') return m.errors
      if (m.errors && typeof m.errors === 'object') {
        const flat = []
        Object.values(m.errors).forEach(v => {
          if (Array.isArray(v)) flat.push(...v)
          else if (v) flat.push(String(v))
        })
        if (flat.length) return flat.join('; ')
      }

      if (m.message) return String(m.message)
      if (m.msg) return String(m.msg)
      if (m.error) return String(m.error)
      try {
        return JSON.stringify(m)
      } catch (ex) {
        return String(m)
      }
    }
    return String(m)
  }

  const showToast = useCallback((message, type = 'info', duration = 4000) => {
    const id = Date.now() + Math.random();
    const text = formatMessage(message)
    const toast = { id, message: text, type, duration };

    setToasts(prev => [...prev, toast]);

    if (duration > 0) {
      const timerId = setTimeout(() => removeToast(id), duration);
      toastTimersRef.current.set(id, timerId)
    }

    return id;
  }, [removeToast]);

  const success = useCallback((message, duration) => showToast(message, 'success', duration), [showToast]);
  const error = useCallback((message, duration) => showToast(message, 'error', duration), [showToast]);
  const info = useCallback((message, duration) => showToast(message, 'info', duration), [showToast]);
  const warning = useCallback((message, duration) => showToast(message, 'warning', duration), [showToast]);
  useEffect(() => {
    const handler = (e) => {
      const { status, body } = e.detail || {}
      const challenge = (body && (body.detail || body)) || null
      const mfaRequired = Boolean(challenge && (challenge.mfa_setup_required === true || (challenge.detail && challenge.detail.mfa_setup_required === true)))
      if (status === 401 && mfaRequired) {
        try {
          if (challenge.setup_token) setSetupToken(challenge.setup_token)
        } catch (_) { /* ignore */ }
        error('Multi‑factor setup is required — please complete 2FA setup to continue.')
        return
      }

      const raw = (body && (body.detail || body.message || body.error || body)) || 'API error'
      const msg = formatMessage(raw)
      if (status >= 400) {
        try {
          const key = `${status}:${msg}`
          if (recentErrorsRef.current.has(key)) return
          recentErrorsRef.current.set(key, Date.now())
          setTimeout(() => recentErrorsRef.current.delete(key), 5000)
          error(msg)
        } catch (ex) {
          console.error('Toast handler error:', ex)
          error(msg)
        }
      }
    }
    globalThis.addEventListener('api-error', handler)
    return () => {
      globalThis.removeEventListener('api-error', handler)
    }
  }, [error])

  useEffect(() => {
    const timers = toastTimersRef.current
    const recentErrors = recentErrorsRef.current
    return () => {
      timers.forEach((timer) => clearTimeout(timer))
      timers.clear()
      recentErrors.clear()
    }
  }, [])

  const value = useMemo(() => ({
    showToast, removeToast, success, error, info, warning
  }), [showToast, removeToast, success, error, info, warning]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed top-4 right-4 z-[100] space-y-2 pointer-events-none">
        {toasts.map(toast => (
          <Toast key={toast.id} message={toast.message} type={toast.type} onClose={() => removeToast(toast.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

ToastProvider.propTypes = {
  children: PropTypes.node.isRequired
};

function Toast({ message, type, onClose }) {
  const variants = {
    success: 'bg-green-500 border-green-600',
    error: 'bg-red-500 border-red-600',
    warning: 'bg-yellow-500 border-yellow-600',
    info: 'bg-blue-500 border-blue-600'
  };

  const icons = {
    success: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
      </svg>
    ),
    error: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
      </svg>
    ),
    warning: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
    info: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    )
  };

  return (
    <div
      className={`pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-lg border-2 text-white shadow-lg animate-slide-in-right min-w-[300px] max-w-md ${variants[type]}`}
    >
      <div className="flex-shrink-0">{icons[type]}</div>
      <div className="flex-1 text-sm font-medium">{message}</div>
      <button
        onClick={onClose}
        className="flex-shrink-0 hover:bg-white/20 rounded p-1 transition-colors"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

Toast.propTypes = {
  message: PropTypes.string.isRequired,
  type: PropTypes.oneOf(['success', 'error', 'warning', 'info']).isRequired,
  onClose: PropTypes.func.isRequired
};
