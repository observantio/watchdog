import { describe, expect, it } from "vitest";
import { computeTraceStats, discoverServices } from "../tempoTraceUtils";

describe("tempoTraceUtils", () => {
  it("discovers unique non-unknown services", () => {
    const services = discoverServices([
      {
        spans: [{ serviceName: "api" }, { process: { serviceName: "db" } }, {}],
      },
    ]);
    expect(services).toEqual(["api", "db"]);
  });

  it("computes trace stats with durations and errors", () => {
    const stats = computeTraceStats([
      {
        spans: [
          { spanId: "1", duration: 100, status: { code: "OK" } },
          {
            spanId: "2",
            parentSpanId: "1",
            duration: 50,
            status: { code: "ERROR" },
          },
        ],
      },
      {
        spans: [{ spanId: "a", duration: 200, status: { code: "OK" } }],
      },
    ]);

    expect(stats.total).toBe(2);
    expect(stats.maxDuration).toBe(200000);
    expect(stats.errorCount).toBe(1);
    expect(stats.errorRate).toBe(50);
  });

  it("returns null for empty traces", () => {
    expect(computeTraceStats([])).toBeNull();
  });
});
