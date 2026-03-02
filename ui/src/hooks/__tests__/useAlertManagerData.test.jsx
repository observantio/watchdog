import { renderHook, waitFor } from "@testing-library/react";
import { vi, describe, it, beforeEach, expect } from "vitest";

vi.mock("../../api", () => ({
  getAlerts: vi.fn(),
  getSilences: vi.fn(),
  getAlertRules: vi.fn(),
  getNotificationChannels: vi.fn(),
}));

import * as api from "../../api";
import { useAlertManagerData } from "../useAlertManagerData";

describe("useAlertManagerData", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads alerts/silences/rules/channels", async () => {
    api.getAlerts.mockResolvedValue([{ id: "a1" }]);
    api.getSilences.mockResolvedValue([{ id: "s1", status: {} }]);
    api.getAlertRules.mockResolvedValue([{ id: "r1" }]);
    api.getNotificationChannels.mockResolvedValue([{ id: "c1" }]);

    const { result } = renderHook(() => useAlertManagerData());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.alerts).toEqual([{ id: "a1" }]);
    expect(result.current.silences).toEqual([{ id: "s1", status: {} }]);
    expect(result.current.rules).toHaveLength(1);
    expect(result.current.rules[0]).toMatchObject({ id: "r1" });
    expect(result.current.channels).toEqual([{ id: "c1" }]);
  });
});
