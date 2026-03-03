import { describe, it, expect, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import OIDCCallbackPage from "../pages/OIDCCallbackPage";
import * as api from "../api";
vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    finishOIDCLogin: async ({ code, state }) => {
      return await api.exchangeOIDCCode(code, "", { state });
    },
  }),
}));

describe("OIDCCallbackPage", () => {
  it("parses querystring before hash correctly", async () => {
    const fakeHref =
      "http://localhost:5173/auth/callback?code=foo&state=bar#/login";
    Object.defineProperty(window, "location", {
      value: { href: fakeHref },
      writable: true,
    });
    vi.spyOn(api, "exchangeOIDCCode").mockResolvedValue({});

    render(
      <MemoryRouter initialEntries={["/auth/callback"]}>
        <Routes>
          <Route path="/auth/callback" element={<OIDCCallbackPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(api.exchangeOIDCCode).toHaveBeenCalled();
      const call = api.exchangeOIDCCode.mock.calls[0];
      expect(call[0]).toBe("foo");
      expect(call[2].state).toBe("bar");
    });
  });
});
