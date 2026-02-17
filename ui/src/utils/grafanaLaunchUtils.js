`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

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
  const encoded = encodeURIComponent(normalizedPath).replace(/%2F/g, '/')
  const tokenParam = encodeURIComponent(token)
  return `${proxyOrigin}/grafana/bootstrap?token=${tokenParam}&next=${encoded}`
}