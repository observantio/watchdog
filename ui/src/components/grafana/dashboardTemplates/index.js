import mimirSystemProcess from "./mimir-system-process.json";
import kubernetesClusterOverview from "./kubernetes-cluster-overview.json";
import httpServiceHealth from "./http-service-health.json";
import lokiLogInsights from "./loki-log-insights.json";
import sloLatencyErrorBudget from "./slo-latency-error-budget.json";
import emptyDashboard from "./empty-dashboard.json";

export const DASHBOARD_TEMPLATES = [
  {
    id: "mimir-system-process",
    name: "System & Process (Mimir)",
    icon: "monitor_heart",
    summary: "Host CPU, memory, disk and network health from Prometheus/Mimir metrics.",
    datasourceUid: "mimir-prometheus",
    dashboard: mimirSystemProcess,
  },
  {
    id: "kubernetes-cluster-overview",
    name: "Kubernetes Cluster Overview",
    icon: "dns",
    summary: "Node and pod status, cluster resource usage and restart hotspots.",
    datasourceUid: "mimir-prometheus",
    dashboard: kubernetesClusterOverview,
  },
  {
    id: "http-service-health",
    name: "HTTP Service Health",
    icon: "monitoring",
    summary: "Traffic, error-rate and latency panels for API/service monitoring.",
    datasourceUid: "mimir-prometheus",
    dashboard: httpServiceHealth,
  },
  {
    id: "slo-latency-error-budget",
    name: "SLO: Latency & Error Budget",
    icon: "speed",
    summary: "Availability, P95/P99 latency and burn-rate view for SLO tracking.",
    datasourceUid: "mimir-prometheus",
    dashboard: sloLatencyErrorBudget,
  },
  {
    id: "loki-log-insights",
    name: "Loki Log Insights",
    icon: "receipt_long",
    summary: "Error/warn log trends with a live log stream for investigation.",
    datasourceUid: "loki",
    dashboard: lokiLogInsights,
  },
  {
    id: "empty",
    name: "Empty Dashboard",
    icon: "dashboard_customize",
    summary: "Start from a blank dashboard.",
    datasourceUid: "",
    dashboard: emptyDashboard,
  },
];
