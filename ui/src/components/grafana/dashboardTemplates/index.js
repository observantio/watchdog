import mimirSystemProcess from "./mimir-system-process.json";

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
];
