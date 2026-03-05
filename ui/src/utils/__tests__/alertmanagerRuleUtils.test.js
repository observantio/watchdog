import { describe, expect, it } from "vitest";
import {
  buildRulePayload,
  normalizeRuleForUI,
  normalizeRuleOrgId,
} from "../alertmanagerRuleUtils";

describe("alertmanagerRuleUtils orgId normalization", () => {
  it("treats empty or default org values as unscoped", () => {
    expect(normalizeRuleOrgId("")).toBeUndefined();
    expect(normalizeRuleOrgId("   ")).toBeUndefined();
    expect(normalizeRuleOrgId("default")).toBeUndefined();
    expect(normalizeRuleOrgId("DEFAULT")).toBeUndefined();
  });

  it("keeps non-default org values", () => {
    expect(normalizeRuleOrgId("org-a")).toBe("org-a");
  });

  it("omits default orgId from create/update payloads", () => {
    const payload = buildRulePayload({
      name: "CPU high",
      orgId: "default",
      expr: "up == 0",
      severity: "warning",
      duration: "1m",
      group: "default",
    });
    expect(payload.orgId).toBeUndefined();
  });

  it("normalizes default orgId from API responses", () => {
    const normalized = normalizeRuleForUI({
      id: "r1",
      name: "CPU high",
      orgId: "default",
      expression: "up == 0",
      severity: "warning",
      groupName: "default",
    });
    expect(normalized.orgId).toBeUndefined();
  });
});
