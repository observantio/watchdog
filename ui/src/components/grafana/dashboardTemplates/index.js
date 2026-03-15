import mimirSystemProcess from "./mimir-system-process.json";
import ojoAgentDashboard from "./ojo-agent-dashboard.json";

export const DASHBOARD_TEMPLATES = [
  {
    id: "mimir-system-process",
    name: "Complete System & Process Observability",
    icon: "monitor_heart",
    summary:
      "Single super-detailed template covering CPU, memory, disk, network, filesystem, paging, and process metrics.",
    datasourceUid: "mimir-prometheus",
    dashboard: mimirSystemProcess,
  },
  {
    id: "ojo-agent-dashboard",
    name: "Ojo Agent Dashboard",
    icon: "visibility",
    summary: "Grafana dashboard for Ojo agent metrics.",
    datasourceUid: "Prometheus",
    dashboard: ojoAgentDashboard,
  },
];
