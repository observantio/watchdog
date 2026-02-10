import { useState } from 'react'
import PropTypes from 'prop-types'
import { Modal, Button, Input, Spinner } from './ui'
import { useToast } from '../contexts/ToastContext'
import * as api from '../api'

export default function ChangePasswordModal({ isOpen, onClose, userId, isForced = false }) {
  const toast = useToast()
  const [loading, setLoading] = useState(false)
  const [showTour, setShowTour] = useState(false)
  const [slideIndex, setSlideIndex] = useState(0)
  const [formData, setFormData] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: ''
  })

  const slides = [
    {
      title: 'A Gentle Observatory',
      body: 'In a world of money-driven monitoring tools, I wanted to create something that puts users first. Be Observant is designed to be simple, transparent, and user-friendly. Using open source components and a clean interface, it gives you powerful observability without the complexity and cost of traditional platforms.'
    },
    {
      title: 'Traces — Threads of Time',
      body: 'With Tempo, we got distributed tracing right at the core. It’s built to handle high volumes of trace data with ease, giving you deep insights into your applications without breaking the bank.'
    },
    {
      title: 'Logs — Stories in Motion',
      body: 'You don’t need to be a logging expert to get value from your logs. With Loki, you can easily search and explore your logs alongside your traces and metrics, all in one place.'
    },
    {
      title: 'Alerts — Quiet Guardians',
      body: 'With Alertmanager, you can set up powerful alerting rules and notifications to stay on top of your system’s health. It’s flexible, reliable, and integrates seamlessly with the rest of the platform.'
    },
    {
      title: 'Dashboards — Windows of Truth',
      body: 'What about dashboards? Be Observant has you covered there too. With Grafana, you can create beautiful, customizable dashboards to visualize your data and share insights with your team.'
    },
    {
      title: 'Teams — Shared Stewardship',
      body: 'We thought about teams too. With robust user management and role-based access control, you can easily manage permissions and keep your data secure. Scope dashboards, channels to specific teams or projects, and ensure everyone has the right level of access.'
    },
    {
      title: 'Open Source — Freedom to Observe',
      body: 'Best of all, Be Observant is open source and self-hosted, giving you full control over your data and your monitoring. No vendor lock-in, no hidden costs, just a powerful observability platform that puts you in the driver’s seat. Support us by starring the project on GitHub and sharing it with your friends and colleagues. Let’s build a better monitoring future together!'
    }
  ]

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    if (formData.newPassword.length < 8) {
      toast.error('Password must be at least 8 characters long')
      return
    }
    
    if (formData.newPassword !== formData.confirmPassword) {
      toast.error('New passwords do not match')
      return
    }
    
    setLoading(true)
    try {
      await api.updateUserPassword(userId, {
        current_password: formData.currentPassword,
        new_password: formData.newPassword
      })
      toast.success('Password updated successfully')
      setFormData({ currentPassword: '', newPassword: '', confirmPassword: '' })
      if (isForced) {
        setShowTour(true)
        setSlideIndex(0)
      } else {
        onClose()
      }
    } finally {
      setLoading(false)
    }
  }

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  let modalTitle;
  if (showTour) {
    modalTitle = slides[slideIndex]?.title || 'Welcome to Be Observant';
  } else if (isForced) {
    modalTitle = 'Password Change Required';
  } else {
    modalTitle = 'Change Password';
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
      className="bg-sre-bg-card rounded-xl shadow-2xl w-full mx-auto border border-sre-border/50 animate-slide-up flex flex-col max-w-2xl"
    >
      {isForced && !showTour && (
        <div className="mb-4 p-3 bg-yellow-500/10 border border-yellow-500 rounded text-yellow-500 text-sm">
          You must change your password before continuing. Please choose a secure password with at least 8 characters.
        </div>
      )}
      {showTour ? (
        <div className="space-y-4">
          <div className="">
            {(() => {
              const slide = slides[slideIndex] || {}
              return (
                <div>
                  <div className="text-sm text-sre-text-muted mt-2">{slide.body}</div>
                </div>
              )
            })()}
          </div>

          <div className="flex items-center justify-between">
            <div className="text-xs text-sre-text-muted">{slideIndex + 1} / {slides.length}</div>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setSlideIndex(i => Math.max(0, i - 1))} disabled={slideIndex === 0}>Prev</Button>
              {slideIndex < slides.length - 1 ? (
                <Button variant="primary" onClick={() => setSlideIndex(i => Math.min(slides.length - 1, i + 1))}>Next</Button>
              ) : (
                <Button variant="primary" onClick={() => { setShowTour(false); if (onClose) onClose(); }}>Done</Button>
              )}
            </div>
          </div>
        </div>
      ) : (
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="currentPassword" className="block text-sm font-medium text-sre-text mb-1">
            Current Password
          </label>
          <Input
            id="currentPassword"
            type="password"
            value={formData.currentPassword}
            onChange={(e) => handleChange('currentPassword', e.target.value)}
            placeholder="Enter current password"
            required
            autoFocus
          />
        </div>

        <div>
          <label htmlFor="newPassword" className="block text-sm font-medium text-sre-text mb-1">
            New Password
          </label>
          <Input
            id="newPassword"
            type="password"
            value={formData.newPassword}
            onChange={(e) => handleChange('newPassword', e.target.value)}
            placeholder="Enter new password (min 8 characters)"
            required
            minLength={8}
          />
        </div>

        <div>
          <label htmlFor="confirmPassword" className="block text-sm font-medium text-sre-text mb-1">
            Confirm New Password
          </label>
          <Input
            id="confirmPassword"
            type="password"
            value={formData.confirmPassword}
            onChange={(e) => handleChange('confirmPassword', e.target.value)}
            placeholder="Confirm new password"
            required
            minLength={8}
          />
        </div>

        <div className="flex gap-3 justify-end pt-4">
          {!isForced && (
            <Button onClick={onClose} variant="ghost" disabled={loading}>
              Cancel
            </Button>
          )}
          <Button type="submit" variant="primary" loading={loading}>
            {loading ? 'Updating...' : 'Update Password'}
          </Button>
        </div>
      </form>
      )}
    </Modal>
  )
}

ChangePasswordModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  userId: PropTypes.string.isRequired,
  isForced: PropTypes.bool
}
