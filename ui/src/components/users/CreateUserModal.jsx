import { useState } from 'react'
import { Modal, Input, Button } from '../ui'
import { useToast } from '../../contexts/ToastContext'
import * as api from '../../api'

export default function CreateUserModal({ isOpen, onClose, onCreated }) {
  const toast = useToast()
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    full_name: '',
    role: 'user'
  })
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState({})

  const generatePassword = () => {
    const length = 16;
    const charset = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*';
    let password = '';
    for (let i = 0; i < length; i++) {
      password += charset.charAt(Math.floor(Math.random() * charset.length));
    }
    return password;
  };

  const handleGeneratePassword = () => {
    const newPassword = generatePassword();
    setFormData({ ...formData, password: newPassword });
    toast.success('Password generated successfully');
  };

  const handleCopyPassword = async () => {
    try {
      await navigator.clipboard.writeText(formData.password);
      toast.success('Password copied to clipboard');
    } catch (err) {
      toast.error('Failed to copy password: ' + (err?.message || 'Unknown error'));
      console.error('Failed to copy password:', err);
    }
  };

  const handleSubmit = async (e) => {
    if (e && typeof e.preventDefault === 'function') e.preventDefault()

    // Client-side validation
    const email = (formData.email || '').trim()
    const password = formData.password || ''
    const username = (formData.username || '').trim()
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    const newErrors = {}
    if (!username) newErrors.username = 'Please enter a username'
    if (!emailRegex.test(email)) newErrors.email = 'Please enter a valid email address'
    if (password.length < 8) newErrors.password = 'Password must be at least 8 characters'
    if (Object.keys(newErrors).length) {
      setErrors(newErrors)
      return
    }

    setLoading(true)

    const formatApiError = (err) => {
      try {
        if (!err) return 'Unknown error'
        // Pydantic detail array
        const detail = err?.body?.detail || err?.detail
        if (Array.isArray(detail)) {
          // also try to map field errors to input-level errors
          const fieldErrs = {}
          const messages = detail.map(d => {
            if (typeof d === 'string') return d
            if (d?.msg) {
              const locArr = Array.isArray(d.loc) ? d.loc : []
              const field = locArr.length ? locArr[locArr.length - 1] : null
              if (field) fieldErrs[field] = d.msg
              const loc = Array.isArray(d.loc) ? d.loc.join('.') : d.loc
              return loc ? `${d.msg} (${loc})` : d.msg
            }
            return JSON.stringify(d)
          })
          if (Object.keys(fieldErrs).length) setErrors(fieldErrs)
          return messages.join('; ')
        }
        if (typeof detail === 'object') {
          if (detail.msg) return detail.msg
          return JSON.stringify(detail)
        }
          if (err?.body?.message) return err.body.message
          if (err?.message) {
          try {
            const parsed = JSON.parse(err.message)
            return parsed.detail || parsed.message || err.message
          } catch (_) {
            return err.message
          }
        }
        return JSON.stringify(err)
      } catch (e) {
        console.error('Error formatting API error', e)
        return 'Unknown error'
      }
    }

    try {
      setErrors({})
      await api.createUser(formData)
      toast.success('User created successfully')
      setFormData({ username: '', email: '', password: '', full_name: '', role: 'user' })
      onCreated && onCreated()
      onClose && onClose()
    } catch (error) {
      const msg = formatApiError(error)
      toast.error('Error creating user: ' + msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create User"
      size="lg"
      footer={
        <div className="flex gap-3 justify-end">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSubmit} loading={loading}>Create User</Button>
        </div>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Input
            label="Username"
            placeholder="stefa"
            value={formData.username}
            onChange={(e) => setFormData({ ...formData, username: e.target.value })}
            required
            error={errors.username}
          />
          <Input
            label="Email"
            placeholder="you@example.com"
            type="email"
            value={formData.email}
            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
            required
            error={errors.email}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <div className="flex-1">
              <Input
                label="Password"
                placeholder="••••••••••••••"
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                required
                error={errors.password}
                helperText="Minimum 8 characters"
                className="w-full"
              />
            </div>
            <div className="flex-shrink-0 flex items-center gap-2">
              <button
                type="button"
                onClick={handleGeneratePassword}
                aria-label="Generate password"
                className="inline-flex items-center justify-center p-2 rounded-md bg-sre-surface hover:bg-sre-surface-light border border-sre-border"
                title="Generate password"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582M20 20v-5h-.581M5.5 9A7.5 7.5 0 0119 12.5M18.5 15A7.5 7.5 0 015 11.5" />
                </svg>
              </button>
              <button
                type="button"
                onClick={handleCopyPassword}
                aria-label="Copy password"
                disabled={!formData.password}
                className="inline-flex items-center justify-center p-2 rounded-md bg-sre-surface hover:bg-sre-surface-light border border-sre-border disabled:opacity-50"
                title="Copy password"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2M16 20h2a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2h6z" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        <Input
          label="Full Name"
          placeholder="Full Name (optional)"
          value={formData.full_name}
          onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
        />

        <div>
          <label className="block text-sm font-medium text-sre-text mb-2">Role</label>
          <select
            value={formData.role}
            onChange={(e) => setFormData({ ...formData, role: e.target.value })}
            className="w-full px-4 py-2 bg-sre-surface border border-sre-border rounded-lg text-sre-text"
          >
            <option value="viewer">Viewer</option>
            <option value="user">User</option>
            <option value="admin">Admin</option>
          </select>
        </div>
      </form>
    </Modal>
  )
}
