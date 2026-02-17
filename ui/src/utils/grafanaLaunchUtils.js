export function normalizeGrafanaPath(path) {
  let rawPath = '/dashboards'

  if (typeof path === 'string' && path.trim()) {
    const trimmedPath = path.trim()
    if (trimmedPath.startsWith('http://') || trimmedPath.startsWith('https://')) {
      try {
        const absoluteUrl = new URL(trimmedPath)
        rawPath = `${absoluteUrl.pathname || '/'}${absoluteUrl.search || ''}${absoluteUrl.hash || ''}`
      } catch {
        rawPath = '/dashboards'
      }
    } else {
      rawPath = trimmedPath.startsWith('/') ? trimmedPath : `/${trimmedPath}`
    }
  }

  let normalizedPath = rawPath.replace(/^\/grafana(?=\/|$)/, '') || '/dashboards'
  if (!normalizedPath.startsWith('/')) {
    normalizedPath = `/${normalizedPath}`
  }
  return normalizedPath
}

import { GRAFANA_URL } from './constants'

export function buildGrafanaLaunchUrl({ path, protocol, hostname }) {
  const normalizedPath = normalizeGrafanaPath(path)
  let grafanaBase = ''
  try {
    const parsed = new URL(GRAFANA_URL)
    grafanaBase = (parsed.pathname || '') .replace(/\/$/, '')
  } catch {
    grafanaBase = '/grafana'
  }
  const proxyOrigin = `${protocol}//${hostname}:8080`
  return `${proxyOrigin}${grafanaBase}${normalizedPath}`
}

export function buildGrafanaBootstrapUrl({ path, protocol, hostname, token }) {
  const normalizedPath = normalizeGrafanaPath(path)
  const proxyOrigin = `${protocol}//${hostname}:8080`
  if (!token) {
    return buildGrafanaLaunchUrl({ path, protocol, hostname })
  }
  // Use the grafana proxy bootstrap endpoint which sets the auth cookie.
  // Keep literal slashes in the `next` param so NGINX's `if ($next_path !~ "^/")`
  // check receives a leading `/` (avoids falling back to `/`). Encode other
  // characters but preserve `/`.
  const encoded = encodeURIComponent(normalizedPath).replace(/%2F/g, '/')
  const tokenParam = encodeURIComponent(token)
  return `${proxyOrigin}/grafana/bootstrap?token=${tokenParam}&next=${encoded}`
}