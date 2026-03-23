import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api", () => ({
  getSystemQuotas: vi.fn(),
}));

const toastMock = { success: vi.fn(), error: vi.fn() };
vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => toastMock,
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      org_id: "org-1",
      api_keys: [
        {
          id: "k1",
          name: "Default",
          key: "org-1",
          is_enabled: true,
          is_shared: false,
          can_use: true,
          is_hidden: false,
        },
      ],
    },
  }),
}));

import * as api from "../../api";
import QuotasPage from "../QuotasPage";

describe("QuotasPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getSystemQuotas).mockResolvedValue({
      api_keys: { current: 2, max: 10, remaining: 8, status: "ok" },
      loki: {
        service: "loki",
        tenant_id: "org-1",
        limit: 100,
        used: 40,
        remaining: 60,
        source: "native",
        status: "ok",
        updated_at: "2026-01-01T00:00:00Z",
        message: null,
      },
      tempo: {
        service: "tempo",
        tenant_id: "org-1",
        limit: 200,
        used: 100,
        remaining: 100,
        source: "prometheus",
        status: "degraded",
        updated_at: "2026-01-01T00:00:00Z",
        message: "fallback in effect",
      },
    });
  });

  it("renders API key and runtime quota values", async () => {
    render(<QuotasPage />);
    expect(await screen.findByText(/Current 2 \/ Max 10/i)).toBeInTheDocument();
    expect(await screen.findByText(/Loki Tenant Quota/i)).toBeInTheDocument();
    expect(await screen.findByText(/Tempo Tenant Quota/i)).toBeInTheDocument();
    expect(await screen.findByText(/fallback in effect/i)).toBeInTheDocument();
  });

  it("refreshes quota payload on demand", async () => {
    render(<QuotasPage />);
    await waitFor(() =>
      expect(api.getSystemQuotas).toHaveBeenCalledWith("org-1"),
    );
    fireEvent.click(await screen.findByRole("button", { name: /Refresh/i }));
    await waitFor(() => expect(api.getSystemQuotas).toHaveBeenCalledTimes(2));
  });
});
