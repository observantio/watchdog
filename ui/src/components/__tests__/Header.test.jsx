import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../api", () => ({
  updateApiKey: vi.fn().mockResolvedValue({}),
  getIncidentsSummary: vi.fn().mockResolvedValue(null),
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: "u1",
      username: "tester",
      role: "admin",
      api_keys: [],
    },
    logout: vi.fn(),
    hasPermission: (permission) => {
      if (permission === "read:agents") return true;
      if (permission === "read:audit_logs") return true;
      return false;
    },
    refreshUser: vi.fn(),
  }),
}));

vi.mock("../ChangePasswordModal", () => ({
  default: () => null,
}));

import Header from "../Header";

describe("Header user menu", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows Quotas link in user dropdown", async () => {
    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /User menu for tester/i }),
    );

    expect(await screen.findByRole("menuitem", { name: /Quotas/i })).toBeInTheDocument();
  });
});
