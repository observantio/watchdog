import { describe, expect, it } from "vitest";
import {
  normalizeGrafanaPath,
  buildGrafanaLaunchUrl,
  buildGrafanaBootstrapUrl,
} from "../grafanaLaunchUtils";

describe("grafana launch utilities", () => {
  it("normalizes absolute grafana URLs into a safe path", () => {
    const path = normalizeGrafanaPath(
      "https://example.com/grafana/d/abc123?orgId=1",
    );
    expect(path).toBe("/d/abc123?orgId=1");
  });

  it("keeps default fallback path for invalid input", () => {
    const path = normalizeGrafanaPath("");
    expect(path).toBe("/dashboards");
  });

  it("builds proxy launch URL without exposing tokens", () => {
    const url = buildGrafanaLaunchUrl({
      path: "/grafana/d/xyz?var-service=api",
      protocol: "http:",
      hostname: "localhost",
    });
    expect(url.startsWith("http://localhost:8080")).toBe(true);
    expect(url).toContain("/d/xyz?var-service=api");
  });

  it("builds grafana bootstrap URL without exposing token", () => {
    const url = buildGrafanaBootstrapUrl({
      path: "/grafana/d/xyz?var-service=api",
      protocol: "http:",
      hostname: "localhost",
    });
    expect(url.startsWith("http://localhost:8080/grafana/bootstrap")).toBe(
      true,
    );
    expect(url).not.toContain("token=");
    // next should include a leading slash (slashes preserved)
    expect(url).toContain("next=/d/xyz%3Fvar-service%3Dapi");
  });
});
