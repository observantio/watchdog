import { describe, expect, it } from "vitest";
import {
  buildServiceGraphData,
  buildServiceGraphInsights,
  buildServiceGraphNodes,
  layoutServiceGraph,
} from "../serviceGraphUtils";

describe("serviceGraphUtils", () => {
  it("builds graph data from spans and parent relationships", () => {
    const traces = [
      {
        traceID: "t1",
        spans: [
          {
            spanId: "1",
            serviceName: "api",
            duration: 200000,
            status: { code: "OK" },
          },
          {
            spanId: "2",
            parentSpanId: "1",
            serviceName: "db",
            duration: 500000,
            status: { code: "ERROR" },
          },
        ],
      },
    ];

    const data = buildServiceGraphData(traces);
    expect(data.services.has("api")).toBe(true);
    expect(data.services.has("db")).toBe(true);
    expect(data.edges.has("api->db")).toBe(true);
  });

  it("builds insights and nodes from graph data", () => {
    const graphData = buildServiceGraphData([
      {
        traceID: "t1",
        spans: [
          {
            spanId: "1",
            serviceName: "api",
            duration: 1000,
            status: { code: "OK" },
          },
          {
            spanId: "2",
            parentSpanId: "1",
            serviceName: "db",
            duration: 2000,
            status: { code: "OK" },
          },
        ],
      },
    ]);

    const insights = buildServiceGraphInsights(graphData);
    expect(Array.isArray(insights.serviceStats)).toBe(true);

    const nodes = buildServiceGraphNodes(graphData);
    expect(nodes.length).toBe(2);

    const layout = layoutServiceGraph(nodes, []);
    expect(layout.nodes.length).toBe(2);
  });
});
