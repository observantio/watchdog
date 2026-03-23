import { describe, expect, it } from "vitest";

import {
  extractMetricNamesFromPromQl,
  ALL_DASHBOARD_METRICS,
  RCA_DEFAULT_METRIC_QUERIES_FROM_DASHBOARDS,
} from "../metricCatalog";

describe("metricCatalog", () => {
  it("extracts metric names but excludes labels and functions", () => {
    const expr =
      'sum(rate(system_cpu_time_seconds_total{state="idle",instance="host-a"}[5m])) by (instance)';
    const metrics = extractMetricNamesFromPromQl(expr);

    expect(metrics).toContain("system_cpu_time_seconds_total");
    expect(metrics).not.toContain("state");
    expect(metrics).not.toContain("instance");
    expect(metrics).not.toContain("sum");
    expect(metrics).not.toContain("rate");
  });

  it("builds dashboard metric and query catalogs", () => {
    expect(ALL_DASHBOARD_METRICS.length).toBeGreaterThan(25);
    expect(ALL_DASHBOARD_METRICS).toContain("system_cpu_time_seconds_total");
    expect(ALL_DASHBOARD_METRICS).toContain("system_memory_available_bytes");

    expect(
      RCA_DEFAULT_METRIC_QUERIES_FROM_DASHBOARDS.some((query) =>
        query.includes("rate(system_cpu_time_seconds_total[5m])"),
      ),
    ).toBe(true);
    expect(
      RCA_DEFAULT_METRIC_QUERIES_FROM_DASHBOARDS.some((query) =>
        query.includes("system_memory_available_bytes"),
      ),
    ).toBe(true);
  });
});
