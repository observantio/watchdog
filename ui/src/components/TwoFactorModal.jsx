`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import { Modal, Button, Input } from './ui'
import { useAuth } from '../contexts/AuthContext'
import * as api from '../api'

export default function TwoFactorModal({ isOpen, onClose, setupMode = false, onVerified = null }) {
  const { user, refreshUser } = useAuth()
  const [enrolling, setEnrolling] = useState(false)
  const [otpauthUrl, setOtpauthUrl] = useState(null)
  const [secret, setSecret] = useState(null)
  const [code, setCode] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isOpen) {
      setEnrolling(false)
      setOtpauthUrl(null)
      setSecret(null)
      setCode('')
      setRecoveryCodes([])
      setLoading(false)
      setError('')
    }
  }, [isOpen])

  const startEnroll = async () => {
    setError('')
    setEnrolling(true)
    try {
      const res = await api.enrollMFA()
      setOtpauthUrl(res.otpauth_url)
      setSecret(res.secret)
    } catch (err) {
      setError(err?.body?.detail || err?.message || 'Failed to start 2FA enrollment')
      setEnrolling(false)
    }
  }

  const verify = async () => {
    setError('')
    setLoading(true)
    try {
      const res = await api.verifyMFA(code)
      setRecoveryCodes(res.recovery_codes || [])
      if (setupMode && typeof onVerified === 'function') {
        // Let caller complete the final login step (login + token issuance)
        onVerified({ code, recoveryCodes: res.recovery_codes || [] })
      } else {
        await refreshUser()
      }
    } catch (err) {
      setError(err?.body?.detail || err?.message || 'Verification failed')
    } finally {
      setLoading(false)
      setEnrolling(false)
    }
  }

  const disable = async () => {
    setError('')
    const current_password = window.prompt('Enter your current password to disable 2FA')
    if (!current_password) return
    setLoading(true)
    try {
      await api.disableMFA({ current_password })
      await refreshUser()
      onClose()
    } catch (err) {
      setError(err?.body?.detail || err?.message || 'Failed to disable 2FA')
    } finally {
      setLoading(false)
    }
  }

  const qrSrc = otpauthUrl ? `https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(otpauthUrl)}&size=200x200` : null

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Two-Factor Authentication" size="md">
      <div className="space-y-4">
        {!user?.mfa_enabled && (
          <div>
            <p className="text-sm text-sre-text-muted mb-3">Protect your account by enabling an authenticator app (TOTP). You will be shown a secret and a QR code to scan.</p>
            {!otpauthUrl && (
              <div className="flex gap-2">
                <Button onClick={startEnroll} loading={enrolling}>Enable 2FA</Button>
              </div>
            )}

            {otpauthUrl && (
              <div className="mt-4 space-y-3">
                <div className="flex items-center gap-4">
                  <div>
                    <img src={qrSrc} alt="TOTP QR code" />
                  </div>
                  <div className="flex-1">
                    <p className="text-xs text-sre-text-muted">Scan the QR code with your authenticator app or enter the secret below manually.</p>
                    <Input value={secret} readOnly />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-sre-text mb-1">Enter code from authenticator</label>
                  <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="123456" />
                </div>

                {error && <div className="text-sm text-red-500">{error}</div>}

                <div className="flex gap-2 mt-2">
                  <Button onClick={verify} loading={loading}>Verify & Enable</Button>
                  <Button variant="ghost" onClick={() => { setOtpauthUrl(null); setSecret(null); setEnrolling(false) }}>Cancel</Button>
                </div>

                {recoveryCodes.length > 0 && (
                  <div className="mt-4 p-3 bg-sre-bg border rounded text-sm">
                    <strong>Recovery codes (store these safely):</strong>
                    <ul className="mt-2 list-disc list-inside">
                      {recoveryCodes.map((c) => <li key={c} className="font-mono text-xs">{c}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {user?.mfa_enabled && (
          <div>
            <p className="text-sm text-sre-text-muted">Two-factor authentication is currently <strong>enabled</strong> for your account.</p>
            <div className="mt-4 flex gap-2">
              <Button variant="danger" onClick={disable}>Disable 2FA</Button>
              <Button variant="ghost" onClick={onClose}>Close</Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}

TwoFactorModal.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
}
