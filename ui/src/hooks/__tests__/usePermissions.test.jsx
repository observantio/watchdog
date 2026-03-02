import { describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from "../../contexts/AuthContext";
import { usePermissions } from "../usePermissions";

describe("usePermissions", () => {
  it("grants all permissions for superuser", () => {
    useAuth.mockReturnValue({ user: { is_superuser: true, permissions: [] } });
    const { result } = renderHook(() => usePermissions());

    expect(result.current.hasPermission("manage:users")).toBe(true);
    expect(result.current.hasAnyPermission(["a", "b"])).toBe(true);
    expect(result.current.hasAllPermissions(["a", "b"])).toBe(true);
    expect(result.current.isSuperuser).toBe(true);
  });

  it("evaluates specific permission sets for regular users", () => {
    useAuth.mockReturnValue({
      user: {
        is_superuser: false,
        permissions: ["read:alerts", "write:alerts"],
      },
    });
    const { result } = renderHook(() => usePermissions());

    expect(result.current.hasPermission("read:alerts")).toBe(true);
    expect(result.current.hasPermission("delete:alerts")).toBe(false);
    expect(
      result.current.hasAnyPermission(["delete:alerts", "read:alerts"]),
    ).toBe(true);
    expect(
      result.current.hasAllPermissions(["read:alerts", "write:alerts"]),
    ).toBe(true);
    expect(result.current.canReadAlerts).toBe(true);
  });
});
