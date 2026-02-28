import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { Card, Spinner } from '../components/ui'

const readParams = () => {
  const url = new URL(globalThis.location.href)
  const search = url.searchParams
  return {
    code: search.get('code') || '',
    state: search.get('state') || '',
    oidcError: search.get('error') || '',
    errorDescription: search.get('error_description') || '',
  }
}

export default function OIDCCallbackPage() {
  const navigate = useNavigate()
  const { finishOIDCLogin } = useAuth()
  const [error, setError] = useState('')

  const params = useMemo(() => readParams(), [])

  useEffect(() => {
    let alive = true

    const run = async () => {
      if (params.oidcError) {
        if (alive) setError(params.errorDescription || params.oidcError)
        return
      }

      if (!params.code || !params.state) {
        if (alive) setError('Missing OIDC callback parameters')
        return
      }

      try {
        await finishOIDCLogin({ code: params.code, state: params.state })
        if (!alive) return
        globalThis.history.replaceState({}, '', '/')
        navigate('/', { replace: true })
      } catch (e) {
        if (alive) setError(e?.message || 'OIDC login failed')
      }
    }

    run()
    return () => {
      alive = false
    }
  }, [finishOIDCLogin, navigate, params])

  return (
    <div className="min-h-screen flex items-center justify-center bg-sre-bg p-4">
      <Card className="w-full max-w-md p-6">
        {!error ? (
          <div className="flex flex-col items-center gap-3 text-center">
            <Spinner size="lg" />
            <h1 className="text-xl font-semibold text-sre-text">Signing you in</h1>
            <p className="text-sre-text-muted text-sm">Completing secure OIDC authentication…</p>
          </div>
        ) : (
          <div className="text-center">
            <h1 className="text-xl font-semibold text-red-500 mb-2">Unable to sign in</h1>
            <p className="text-sre-text-muted text-sm mb-4">{error}</p>
            <button
              type="button"
              className="text-sre-primary hover:text-sre-primary-light"
              onClick={() => navigate('/login', { replace: true })}
            >
              Back to login
            </button>
          </div>
        )}
      </Card>
    </div>
  )
}