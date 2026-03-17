import native from "./native.json";
import linux from "./linux.json";
import windows from "./windows.json";

export const DASHBOARD_TEMPLATES = [
  {
    id: "native-otel-collector-overview",
    name: "OTel Collector Overview",
    icon: "monitor_heart",
    summary:
      "Single super-detailed template covering CPU, memory, disk, network, filesystem, paging, and process metrics.",
    datasourceUid: "mimir-prometheus",
    dashboard: native,
  },
  {
    id: "linux-collector-overview",
    name: "Linux Collector Overview",
    icon: "visibility",
    summary: "Grafana dashboard for Linux collector metrics using the Observantio Collector.",
    datasourceUid: "Prometheus",
    dashboard: linux,
  },
  {
    id: "windows-collector-overview",
    name: "Windows Collector Overview",
    icon: "visibility",
    summary: "Grafana dashboard for Windows collector metrics using the Observantio Collector.",
    datasourceUid: "Prometheus",
    dashboard: windows,
  },
];
