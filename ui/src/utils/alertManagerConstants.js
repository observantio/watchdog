`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

export const ALERT_TEMPLATES = [
  {
    name: 'Memory Usage',
    yaml: `groups:\n  - name: core-services-memory\n    rules:\n      - alert: HighMemoryUsage\n        expr: |\n          (\n            node_memory_MemTotal_bytes\n            - node_memory_MemAvailable_bytes\n          )\n          / node_memory_MemTotal_bytes > 0.80\n        for: 5m\n        labels:\n          severity: warning\n          service: core\n          resource: memory\n        annotations:\n          summary: High memory usage detected\n          description: >\n            Memory usage has exceeded 80% for more than 5 minutes.\n            This may indicate memory leaks, pod overcommitment, or insufficient node sizing.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]\n\n      - alert: CriticalMemoryUsage\n        expr: |\n          (\n            node_memory_MemTotal_bytes\n            - node_memory_MemAvailable_bytes\n          )\n          / node_memory_MemTotal_bytes > 0.92\n        for: 3m\n        labels:\n          severity: critical\n          service: core\n          resource: memory\n        annotations:\n          summary: Critical memory pressure\n          description: >\n            Memory usage is above 92%. OOM events are likely.\n            Immediate investigation required.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]`
  },
  {
    name: 'CPU Usage',
    yaml: `groups:\n  - name: core-services-cpu\n    rules:\n      - alert: HighCPUUsage\n        expr: avg(rate(cpu_seconds_total[5m])) > 0.80\n        for: 5m\n        labels:\n          severity: warning\n          service: core\n          resource: cpu\n        annotations:\n          summary: High CPU usage detected\n          description: >\n            CPU usage has exceeded 80% for more than 5 minutes.\n            This may indicate performance issues or insufficient CPU resources.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]\n\n      - alert: CriticalCPUUsage\n        expr: avg(rate(cpu_seconds_total[5m])) > 0.95\n        for: 3m\n        labels:\n          severity: critical\n          service: core\n          resource: cpu\n        annotations:\n          summary: Critical CPU usage\n          description: >\n            CPU usage is above 95%. System may become unresponsive.\n            Immediate action required.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]`
  },
  {
    name: 'Disk Space',
    yaml: `groups:\n  - name: infrastructure-disk\n    rules:\n      - alert: LowDiskSpace\n        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.15\n        for: 10m\n        labels:\n          severity: warning\n          service: infrastructure\n          resource: disk\n        annotations:\n          summary: Low disk space\n          description: >\n            Disk space is below 15%. Consider cleaning up old files or expanding storage.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]\n\n      - alert: CriticalDiskSpace\n        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.05\n        for: 5m\n        labels:\n          severity: critical\n          service: infrastructure\n          resource: disk\n        annotations:\n          summary: Critical disk space\n          description: >\n            Disk space is below 5%. System may fail to write data.\n            Immediate cleanup or expansion required.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]`
  },
  {
    name: 'Service Availability',
    yaml: `groups:\n  - name: service-availability\n    rules:\n      - alert: ServiceDown\n        expr: up == 0\n        for: 2m\n        labels:\n          severity: critical\n          service: monitoring\n        annotations:\n          summary: Service is down\n          description: >\n            The service has been down for more than 2 minutes.\n            Check service logs and restart if necessary.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]\n\n      - alert: HighErrorRate\n        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05\n        for: 5m\n        labels:\n          severity: warning\n          service: api\n        annotations:\n          summary: High error rate\n          description: >\n            Error rate exceeds 5% for more than 5 minutes.\n            Investigate API issues or database connectivity.\n        beobservant:\n          visibility: private\n          orgId: Av45ZchZsQdKjN8XyG\n          channels: ["channel-id"]\n          sharedGroupIds: ["group-id"]`
  }
]

export const TABS_CONFIG = [
  { key: 'alerts', label: 'Alerts', icon: 'notification_important' },
  { key: 'rules', label: 'Rules', icon: 'rule' },
  { key: 'silences', label: 'Silences', icon: 'volume_off' }
]

export const METRIC_DATA = {
  activeAlerts: { label: 'Active Alerts', icon: 'warning' },
  alertRules: { label: 'Alert Rules', icon: 'rule' },
  silences: { label: 'Active Silences', icon: 'volume_off' }
}

export const getSeverityVariant = (severity) => {
  switch (severity) {
    case 'critical': return 'error'
    case 'warning': return 'warning'
    default: return 'info'
  }
}