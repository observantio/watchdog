import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'

function jsonResponse(payload, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'ERR',
    headers: { get: (name) => (name.toLowerCase() === 'content-type' ? 'application/json' : null) },
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  }
}

describe('api request behavior', () => {
  beforeEach(() => {
    api.setAuthToken(null)
    api.setUserOrgIds([])
    api.setSetupToken(null)
    vi.restoreAllMocks()
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ ok: true })))
  })

  it('sends credentials and authorization header when token is set', async () => {
    api.setAuthToken('token-123')
    await api.getCurrentUser()

    expect(fetch).toHaveBeenCalledTimes(1)
    const [, options] = fetch.mock.calls[0]
    expect(options.credentials).toBe('include')
    expect(options.headers.Authorization).toBe('Bearer token-123')
  })

  it('sends credentials but no Authorization header when token is not set (cookie sessions)', async () => {
    api.setAuthToken(null)
    await api.getCurrentUser()

    expect(fetch).toHaveBeenCalledTimes(1)
    const [, options] = fetch.mock.calls[0]
    expect(options.credentials).toBe('include')
    expect(options.headers.Authorization).toBeUndefined()
  })

  it('adds X-Scope-OrgID for Loki/Tempo requests', async () => {
    api.setAuthToken('token-abc')
    api.setUserOrgIds(['org-a'])

    await api.queryLogs({ query: '{job="api"}', limit: 5 })

    const [, options] = fetch.mock.calls[0]
    expect(options.headers['X-Scope-OrgID']).toBe('org-a')
    expect(options.headers.Authorization).toBe('Bearer token-abc')
  })

  it('throws structured error body on non-2xx', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'Denied' }, 403)))

    await expect(api.getCurrentUser()).rejects.toMatchObject({
      status: 403,
      body: { detail: 'Denied' },
    })
  })
})
