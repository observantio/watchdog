`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { useState } from 'react'
import PropTypes from 'prop-types'
import { Modal, Button, Input } from './ui'
import { useToast } from '../contexts/ToastContext'
import HelpTooltip from './HelpTooltip'
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
      body: 'With Be Notified built on top of Alertmanager, you can set up powerful alerting rules and notifications to stay on top of your system’s health. It’s flexible, reliable, and integrates seamlessly with the rest of the platform. It can ingest alerts from any source, so you can centralize your alerting and never miss a critical issue again.'
    },
    {
      title: 'Dashboards — Windows of Truth',
      body: 'What about dashboards? Be Observant has you covered there too. With Grafana, you can create beautiful, customizable dashboards to visualize your data and share insights with your team.'
    },
    {
      title: 'RCA — Root Cause Analysis',
      body: 'With Be Certain, you can easily identify and resolve issues quickly. Our integrated root cause analysis tools help you understand the underlying causes of problems, so you can fix them faster and prevent future occurrences. It is runs AI powered RCA on your traces and logs, giving you actionable insights to resolve incidents faster than ever before.'
    },
    {
      title: 'Teams — Shared Stewardship',
      body: 'We thought about teams too. With robust user management and role-based access control, you can easily manage permissions and keep your data secure. Scope dashboards, channels to specific teams or projects, and ensure everyone has the right level of access.'
    },
    {
      title: 'Open Source — Freedom to Observe',
      body: 'Best of all, Be Observant is open source and self-hosted, giving you full control over your data and your monitoring. No vendor lock-in, no hidden costs, just a powerful observability platform that puts you in the driver’s seat. You will only be running to costs to run these servers. Support us by starring the project on GitHub and sharing it with your friends and colleagues.  Let’s build a better monitoring future together!'
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
    } catch (err) {
      toast.error(err?.body?.detail || err?.message || 'Password update failed')
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
                  <div className="text-sm text-sre-text-muted">{slide.body}</div>
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
          <div className="flex items-center gap-2 mb-1">
            <label htmlFor="currentPassword" className="block text-sm font-medium text-sre-text">
              Current Password
            </label>
            <HelpTooltip text="Enter your current password to verify your identity before changing it." />
          </div>
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
          <div className="flex items-center gap-2 mb-1">
            <label htmlFor="newPassword" className="block text-sm font-medium text-sre-text">
              New Password
            </label>
            <HelpTooltip text="Choose a strong password with at least 12 characters, including uppercase, lowercase, numbers, and special characters." />
          </div>
          <Input
            id="newPassword"
            type="password"
            value={formData.newPassword}
            onChange={(e) => handleChange('newPassword', e.target.value)}
            placeholder="Enter new password (min 12 characters)"
            required
            minLength={12}
          />
        </div>

        <div>
          <div className="flex items-center gap-2 mb-1">
            <label htmlFor="confirmPassword" className="block text-sm font-medium text-sre-text">
              Confirm New Password
            </label>
            <HelpTooltip text="Re-enter your new password to ensure it matches exactly." />
          </div>
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
