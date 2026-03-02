import { describe, expect, it } from "vitest";
import {
  DEFAULT_ALERTMANAGER_METRIC_KEYS,
  normalizeChannelPayload,
  readMetricOrderFromStorage,
  writeMetricOrderToStorage,
} from "../alertmanagerChannelUtils";

describe("alertmanagerChannelUtils", () => {
  it("normalizes config aliases into server keys", () => {
    const payload = normalizeChannelPayload({
      type: "slack",
      config: { webhookUrl: "https://hooks.slack.test" },
    });
    expect(payload.config.webhook_url).toBe("https://hooks.slack.test");
  });

  it("reads default metric order on invalid storage payload", () => {
    const storage = {
      getItem: () => "not-json",
      setItem: () => {},
    };
    expect(readMetricOrderFromStorage(storage)).toEqual(
      DEFAULT_ALERTMANAGER_METRIC_KEYS,
    );
  });

  it("writes metric order safely", () => {
    const writes = [];
    const storage = {
      getItem: () => null,
      setItem: (k, v) => writes.push([k, v]),
    };
    writeMetricOrderToStorage(
      ["channels", "silences", "activeAlerts", "alertRules"],
      storage,
    );
    expect(writes.length).toBe(1);
  });
});
