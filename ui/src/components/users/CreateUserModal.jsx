import { useState } from 'react'
import { Modal, Input, Button, Checkbox } from '../ui'
import { useToast } from '../../contexts/ToastContext'
import { useAuth } from '../../contexts/AuthContext'
import HelpTooltip from '../HelpTooltip'
import * as api from '../../api'
import { copyToClipboard } from '../../utils/helpers'
import {
  USERNAME_REGEX,
  generateStrongPassword,
  validateCreateUserForm,
  buildCreateUserPayload,
} from './createUserFormUtils'
import { USER_ROLES } from '../../utils/constants'

export default function CreateUserModal({ isOpen, onClose, onCreated, groups = [], users = [] }) {
  const toast = useToast()
  const { authMode } = useAuth()
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    full_name: '',
    role: 'user',
    group_ids: [],
    must_setup_mfa: false,
  })
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState({})
  const [groupSearchQuery, setGroupSearchQuery] = useState('')
  const isOidcEnabled = Boolean(authMode?.oidc_enabled)
  const isPasswordEnabled = Boolean(authMode?.password_enabled)
  const requirePassword = !isOidcEnabled || isPasswordEnabled

  // Filter and limit groups
  const filteredGroups = groups.filter(group => {
    const query = groupSearchQuery.toLowerCase()
    return group.name.toLowerCase().includes(query) || 
           (group.description && group.description.toLowerCase().includes(query))
  })
  const displayedGroups = filteredGroups.slice(0, 5)
  const hasMoreGroups = filteredGroups.length > 5

  const handleGeneratePassword = () => {
    const newPassword = generateStrongPassword()
    setFormData({ ...formData, password: newPassword })
    toast.success('Password generated successfully');
  };

  const handleCopyPassword = async () => {
    try {
      const copied = await copyToClipboard(formData.password)
      if (!copied) {
        throw new Error('Clipboard is unavailable in this browser context')
      }
      toast.success('Password copied to clipboard');
    } catch (err) {
      toast.error('Failed to copy password: ' + (err?.message || 'Unknown error'));
    }
  };

  const handleSubmit = async (e) => {
    if (e && typeof e.preventDefault === 'function') e.preventDefault()

    const { normalized, errors: newErrors } = validateCreateUserForm(formData, { requirePassword })
    if (Object.keys(newErrors).length) {
      setErrors(newErrors)
      return
    }

    const payload = buildCreateUserPayload(normalized, {
      includePassword: Boolean(normalized.password),
    })


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
      } catch {
        return 'Unknown error'
      }
    }

    try {
      setErrors({})
      await api.createUser(payload)
      toast.success('User created successfully')
      setFormData({ username: '', email: '', password: '', full_name: '', role: 'user', group_ids: [] })
      setGroupSearchQuery('')
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
      closeOnOverlayClick={false}
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
          <div className="flex items-start gap-2">
            <div className="flex-1">
              <Input
                label="Username"
                placeholder="Username"
                value={formData.username}
                onChange={(e) => {
                  const val = e.target.value
                  const lower = val.toLowerCase()
                  setFormData({ ...formData, username: lower })
                  // live validation
                  if (errors.username) {
                    if (lower && USERNAME_REGEX.test(lower)) {
                      const nextErrors = { ...errors }
                      delete nextErrors.username
                      setErrors(nextErrors)
                    }
                  }
                }}
                required
                error={errors.username}
              />
            </div>
            <HelpTooltip text="Unique username for login. Must be 3-50 characters, lowercase letters, numbers, dots, underscores, or hyphens only." />
          </div>
          <div className="flex items-start gap-2">
            <div className="flex-1">
              <Input
                label="Email"
                placeholder="me@company.com"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                required
                error={errors.email}
              />
            </div>
            <HelpTooltip text="Primary email address for account notifications and password recovery." />
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-start gap-2">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <div className="flex-1">
                  <Input
                    label="Password"
                    placeholder="••••••••••••••"
                    type="password"
                    value={formData.password}
                    onChange={(e) => {
                      const val = e.target.value
                      setFormData({ ...formData, password: val })
                      if (errors.password && val.length >= 8) {
                        const nextErrors = { ...errors }
                        delete nextErrors.password
                        setErrors(nextErrors)
                      }
                    }}
                    required={requirePassword}
                    error={errors.password}
                    helperText={!errors.password && (formData.password || '').length < 8 && requirePassword
                      ? `${8 - (formData.password || '').length} characters to go`
                      : undefined}
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
            <HelpTooltip text="Secure password for account access. Must be at least 8 characters. Use the generate button for a strong random password." />
          </div>
          {isOidcEnabled && !isPasswordEnabled && (
            <p className="text-xs text-sre-text-muted">
              OIDC is enabled and password login is disabled. Leave password blank to create an externally managed user.
            </p>
          )}
        </div>

        <div className="flex items-start gap-2">
          <div className="flex-1">
            <Input
              label="Full Name"
              placeholder="Full Name (optional)"
              value={formData.full_name}
              onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
            />
          </div>
          <HelpTooltip text="Display name shown throughout the interface. Optional field for better user identification." />
        </div>

        <div className="flex items-start gap-2">
          <div className="flex-1">
            <label htmlFor="role" className="block text-sm font-medium text-sre-text mb-2">Role</label>
            <select
                id="role"
                value={formData.role}
                onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                className="w-full max-w-xs rounded border border-sre-border bg-sre-bg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sre-primary"
              >
                {USER_ROLES.map(r => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
          </div>
          <HelpTooltip text="Roles provide baseline permissions. Admin has full access to all features, User can read and modify most resources, Viewer has read-only access." />
        </div>

        <div className="flex items-center gap-3">
          <Checkbox checked={formData.must_setup_mfa} onChange={() => setFormData({ ...formData, must_setup_mfa: !formData.must_setup_mfa })} label="Require Two‑Factor on first login" />
          <HelpTooltip text="When enabled the user will be required to enroll in 2FA at their next login." />
        </div>

        <div>
          <div className="flex items-center gap-2 mb-2">
            <label className="block text-sm font-medium text-sre-text">Groups (optional)</label>
            <HelpTooltip text="Assign user to groups for additional permissions beyond their role. Users inherit all permissions from assigned groups." />
          </div>
          
          {groups.length > 0 && (
            <div className="mb-3">
              <Input
                placeholder="Search groups..."
                value={groupSearchQuery}
                onChange={(e) => setGroupSearchQuery(e.target.value)}
                className="text-sm"
              />
            </div>
          )}
          
          <div className="max-h-48 overflow-y-auto bg-sre-surface">
            {groups.length === 0 && (
              <p className="text-sm text-sre-text-muted">No groups available</p>
            )}
            {filteredGroups.length === 0 && groups.length > 0 && (
              <p className="text-sm text-sre-text-muted">No groups match your search</p>
            )}
            <div className="grid gap-3 grid-cols-2">
              {displayedGroups.map((group) => (
                <div
                  key={group.id}
                  role="checkbox"
                  tabIndex={0}
                  aria-checked={formData.group_ids.includes(group.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      const next = new Set(formData.group_ids)
                      if (next.has(group.id)) next.delete(group.id)
                      else next.add(group.id)
                      setFormData({ ...formData, group_ids: Array.from(next) })
                    }
                  }}
                  className="flex items-start gap-3 p-4 bg-gradient-to-r from-sre-surface to-sre-surface/80 border-2 border-sre-border/50 hover:border-sre-primary/30 hover:shadow-md transition-all duration-200 backdrop-blur-sm rounded-lg cursor-pointer focus:outline-none focus:ring-2 focus:ring-sre-primary/50"
                  onClick={() => {
                    const next = new Set(formData.group_ids)
                    if (next.has(group.id)) {
                      next.delete(group.id)
                    } else {
                      next.add(group.id)
                    }
                    setFormData({ ...formData, group_ids: Array.from(next) })
                  }}
                >
                  <div className="flex-shrink-0 pt-1">
                    <Checkbox
                      checked={formData.group_ids.includes(group.id)}
                      onChange={(e) => {
                        e.stopPropagation()
                        const next = new Set(formData.group_ids)
                        if (next.has(group.id)) {
                          next.delete(group.id)
                        } else {
                          next.add(group.id)
                        }
                        setFormData({ ...formData, group_ids: Array.from(next) })
                      }}
                    />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <div className="w-8 h-8 rounded-md bg-sre-primary/10 text-sre-primary flex items-center justify-center font-semibold text-sm border border-sre-border/50">
                        <span className="material-icons text-base">groups</span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-sre-text text-sm truncate" title={group.name}>{group.name}</div>
                        <div className="text-xs text-sre-text-muted">
                          {(() => { const n = (users || []).filter(u => (u.group_ids || []).includes(group.id)).length; return `${n} member${n === 1 ? '' : 's'}` })()}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {hasMoreGroups && (
              <div className="text-xs text-sre-text-muted text-center py-2 mt-2 border-t border-sre-border">
                Showing first 5 of {filteredGroups.length} groups. Use search to find specific groups.
              </div>
            )}
          </div>
        </div>
      </form>
    </Modal>
  )
}
