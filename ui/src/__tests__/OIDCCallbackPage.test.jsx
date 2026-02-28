import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import OIDCCallbackPage from '../pages/OIDCCallbackPage'
import { AuthProvider, useAuth } from '../contexts/AuthContext'
import * as api from '../api'

// we'll watch the call to the backend since finishOIDCLogin forwards the
// parameters it parsed from the URL.

describe('OIDCCallbackPage', () => {
  it('parses querystring before hash correctly', async () => {
    // craft a fake URL which simulates the problem seen in the issue
    const fakeHref = 'http://localhost:5173/auth/callback?code=foo&state=bar#/login'
    Object.defineProperty(window, 'location', {
      value: { href: fakeHref },
      writable: true,
    })

    // mock backend exchange so we can assert on the args it receives
    api.exchangeOIDCCode.mockResolvedValue({})

    render(
      <MemoryRouter initialEntries={["/auth/callback"]}>
        <AuthProvider>
          <Routes>
            <Route path="/auth/callback" element={<OIDCCallbackPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(api.exchangeOIDCCode).toHaveBeenCalled()
      const call = api.exchangeOIDCCode.mock.calls[0]
      expect(call[0]).toBe('foo')
      expect(call[2].state).toBe('bar')
    })
  })
})
