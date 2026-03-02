export function normalizeGrafanaPath(path) {
  let rawPath = "/dashboards";

  if (typeof path === "string" && path.trim()) {
    const trimmedPath = path.trim();
    if (
      trimmedPath.startsWith("http://") ||
      trimmedPath.startsWith("https://")
    ) {
      try {
        const absoluteUrl = new URL(trimmedPath);
        rawPath = `${absoluteUrl.pathname || "/"}${absoluteUrl.search || ""}${absoluteUrl.hash || ""}`;
      } catch {
        rawPath = "/dashboards";
      }
    } else {
      rawPath = trimmedPath.startsWith("/") ? trimmedPath : `/${trimmedPath}`;
    }
  }

  let normalizedPath =
    rawPath.replace(/^\/grafana(?=\/|$)/, "") || "/dashboards";
  if (!normalizedPath.startsWith("/")) {
    normalizedPath = `/${normalizedPath}`;
  }
  return normalizedPath;
}

import { GRAFANA_URL } from "./constants";

export function buildGrafanaLaunchUrl({ path, protocol, hostname }) {
  const normalizedPath = normalizeGrafanaPath(path);
  let grafanaBase = "";
  try {
    const parsed = new URL(GRAFANA_URL);
    grafanaBase = (parsed.pathname || "").replace(/\/$/, "");
  } catch {
    grafanaBase = "/grafana";
  }
  const proxyOrigin = `${protocol}//${hostname}:8080`;
  return `${proxyOrigin}${grafanaBase}${normalizedPath}`;
}

export function buildGrafanaBootstrapUrl({ path, protocol, hostname }) {
  const normalizedPath = normalizeGrafanaPath(path);
  const proxyOrigin = `${protocol}//${hostname}:8080`;
  const encoded = encodeURIComponent(normalizedPath).replace(/%2F/g, "/");
  return `${proxyOrigin}/grafana/bootstrap?next=${encoded}`;
}
