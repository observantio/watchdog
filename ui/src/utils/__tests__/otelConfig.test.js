import { describe, it, expect } from "vitest";
import { buildOtelYaml } from "../otelConfig";

describe("buildOtelYaml", () => {
  it("inserts placeholder/comment when otlp token is empty", () => {
    const yaml = buildOtelYaml("", {
      lokiEndpoint: "http://loki",
      tempoEndpoint: "http://tempo",
      mimirEndpoint: "http://mimir",
    });
    expect(yaml).toContain("# x-otlp-token: <not available>");
  });
});
