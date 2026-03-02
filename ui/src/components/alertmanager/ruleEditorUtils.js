export const DURATION_PATTERN = /^(\d+ms|\d+s|\d+m|\d+h|\d+d|\d+w|\d+y)+$/;

export const RULE_TEMPLATES = [
  {
    id: "cpu-system",
    name: "High CPU (system)",
    expr: '100 - (avg without (cpu, state) (rate(system_cpu_time_seconds_total{state="idle"}[1m])) * 100) > 80',
    duration: "2m",
    severity: "warning",
    summary: "High CPU utilization",
    description: "CPU busy (non-idle) above 80% for 2 minutes.",
  },
  {
    id: "cpu-node",
    name: "High CPU (node exporter)",
    expr: 'avg by (instance) (rate(node_cpu_seconds_total{mode="system"}[5m])) * 100 > 80',
    duration: "5m",
    severity: "warning",
    summary: "High node CPU",
    description: "Node CPU system time above 80% for 5 minutes.",
  },
  {
    id: "memory-high",
    name: "High Memory Usage",
    expr: "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100 > 90",
    duration: "5m",
    severity: "critical",
    summary: "High memory utilization",
    description:
      "Memory usage above 90% for 5 minutes. System may become unresponsive.",
  },
  {
    id: "disk-space-low",
    name: "Low Disk Space",
    expr: '(node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100 < 10',
    duration: "10m",
    severity: "warning",
    summary: "Low disk space on root filesystem",
    description: "Root filesystem has less than 10% space available.",
  },
  {
    id: "service-down",
    name: "Service Down",
    expr: 'up{job="my-service"} == 0',
    duration: "1m",
    severity: "critical",
    summary: "Service is down",
    description: "Target service is not responding to Prometheus scrapes.",
  },
  {
    id: "http-5xx-rate",
    name: "High 5xx Error Rate",
    expr: 'sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.05',
    duration: "5m",
    severity: "critical",
    summary: "Elevated 5xx error rate",
    description: "More than 5% of requests are failing with 5xx responses.",
  },
  {
    id: "database-connections-high",
    name: "High Database Connections",
    expr: "max_over_time(pg_stat_activity_count[5m]) > 100",
    duration: "2m",
    severity: "warning",
    summary: "High database connection count",
    description: "Database has more than 100 active connections.",
  },
  {
    id: "network-errors",
    name: "Network Interface Errors",
    expr: "rate(node_network_receive_errs_total[5m]) + rate(node_network_transmit_errs_total[5m]) > 10",
    duration: "5m",
    severity: "warning",
    summary: "Network interface errors detected",
    description: "Network interface is experiencing packet errors.",
  },
  {
    id: "certificate-expiry",
    name: "SSL Certificate Expiring Soon",
    expr: "probe_ssl_earliest_cert_expiry - time() < 86400 * 7",
    duration: "1h",
    severity: "warning",
    summary: "SSL certificate expires within 7 days",
    description: "SSL certificate will expire in less than 7 days.",
  },
  {
    id: "response-time-high",
    name: "High Response Time",
    expr: "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 2",
    duration: "5m",
    severity: "warning",
    summary: "95th percentile response time > 2s",
    description: "95% of requests are taking longer than 2 seconds.",
  },
  {
    id: "queue-depth-high",
    name: "High Queue Depth",
    expr: 'rabbitmq_queue_messages_ready{queue="my-queue"} > 1000',
    duration: "3m",
    severity: "warning",
    summary: "Message queue depth is high",
    description: "Queue has more than 1000 messages waiting to be processed.",
  },
  {
    id: "disk-io-high",
    name: "High Disk I/O Wait",
    expr: "rate(node_disk_io_time_seconds_total[1m]) / rate(node_disk_io_time_weighted_seconds_total[1m]) > 0.1",
    duration: "5m",
    severity: "warning",
    summary: "High disk I/O wait time",
    description: "Disk I/O wait time is above 10% of total time.",
  },
  {
    id: "pod-restarts-high",
    name: "High Pod Restart Rate",
    expr: "increase(kube_pod_container_status_restarts_total[10m]) > 5",
    duration: "5m",
    severity: "warning",
    summary: "Pods restarting frequently",
    description:
      "Kubernetes pods have restarted more than 5 times in the last 10 minutes.",
  },
  {
    id: "api-rate-limit",
    name: "API Rate Limit Hit",
    expr: 'rate(http_requests_total{status="429"}[1m]) > 10',
    duration: "1m",
    severity: "warning",
    summary: "API rate limit exceeded",
    description: "API is returning 429 status codes at a high rate.",
  },
  {
    id: "memory-leak",
    name: "Potential Memory Leak",
    expr: "increase(process_resident_memory_bytes[1h]) > 100 * 1024 * 1024",
    duration: "30m",
    severity: "warning",
    summary: "Memory usage increasing rapidly",
    description:
      "Process memory has increased by more than 100MB in the last hour.",
  },
  {
    id: "log-errors-high",
    name: "High Error Log Rate",
    expr: 'sum(rate(log_messages_total{level="error"}[5m])) > 100',
    duration: "5m",
    severity: "critical",
    summary: "High rate of error log messages",
    description: "More than 100 error messages logged per second.",
  },
];

export const DEFAULT_FORM = {
  name: "",
  orgId: "",
  expr: "",
  duration: "1m",
  severity: "warning",
  labels: {},
  annotations: { summary: "", description: "" },
  enabled: true,
  group: "default",
  notificationChannels: [],
  visibility: "private",
  sharedGroupIds: [],
};

const VALID_SEVERITIES = new Set(["info", "warning", "critical"]);

export function validateRuleForm(data, labelPairs) {
  const errors = {};
  const warnings = [];

  if (!data.name || !data.name.trim()) {
    errors.name = "Rule name is required.";
  } else if (data.name.trim().length > 100) {
    errors.name = "Rule name must be 100 characters or fewer.";
  }

  if (!data.expr || !data.expr.trim()) {
    errors.expr = "PromQL expression is required.";
  }

  if (data.duration && !DURATION_PATTERN.test(data.duration)) {
    errors.duration =
      "Duration must use Prometheus format (e.g., 5m, 1h, 30s).";
  }

  if (!VALID_SEVERITIES.has(data.severity)) {
    errors.severity = "Severity must be info, warning, or critical.";
  }

  const expr = data.expr || "";
  let depth = 0;
  for (const ch of expr) {
    if (ch === "(") depth += 1;
    if (ch === ")") depth -= 1;
    if (depth < 0) break;
  }
  if (depth !== 0) {
    errors.expr = errors.expr || "Unbalanced parentheses in expression.";
  }

  if (!/[<>!=]=?|==/.test(expr)) {
    warnings.push(
      "Expression has no comparison operator; alert may never fire.",
    );
  }
  if (
    /(\brate\s*\(|\birate\s*\(|\bincrease\s*\(|\bdelta\s*\()/.test(expr) &&
    !/\[[0-9]+(ms|s|m|h|d|w|y)\]/.test(expr)
  ) {
    warnings.push(
      "Rate/increase functions usually need a range selector like [5m].",
    );
  }
  if (!data.annotations?.summary) {
    warnings.push("Summary is empty; notifications will be less clear.");
  }

  const labelKeys = new Set();
  const duplicateLabels = [];
  labelPairs.forEach(({ key }) => {
    const trimmed = key.trim();
    if (!trimmed) return;
    if (labelKeys.has(trimmed)) duplicateLabels.push(trimmed);
    labelKeys.add(trimmed);
  });
  if (duplicateLabels.length > 0) {
    errors.labels = `Duplicate label keys: ${duplicateLabels.join(", ")}`;
  }

  return { errors, warnings };
}

export function createLabelPairsFromRule(rule) {
  const entries = Object.entries(rule?.labels || {});
  return entries.map(([key, value], index) => ({
    id: `label-${index}-${key}`,
    key,
    value,
  }));
}
