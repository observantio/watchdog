import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import OIDCCallbackPage from "../pages/OIDCCallbackPage";
// we'll stub the auth context in the test below
import * as api from "../api";

// we'll watch the call to the backend since finishOIDCLogin forwards the
// parameters it parsed from the URL.

// mock the auth context so we can intercept finishOIDCLogin without relying on
// stored session values
vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    finishOIDCLogin: async ({ code, state }) => {
      // simply delegate to the real API helper so we can assert on it
      return await api.exchangeOIDCCode(code, "", { state });
    },
  }),
}));

describe("OIDCCallbackPage", () => {
  it("parses querystring before hash correctly", async () => {
    // craft a fake URL which simulates the problem seen in the issue
    const fakeHref =
      "http://localhost:5173/auth/callback?code=foo&state=bar#/login";
    Object.defineProperty(window, "location", {
      value: { href: fakeHref },
      writable: true,
    });

    // no need to prepopulate sessionStorage since auth context is stubbed

    // mock backend exchange so we can assert on the args it receives
    // ensure the function is a spyable mock
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
