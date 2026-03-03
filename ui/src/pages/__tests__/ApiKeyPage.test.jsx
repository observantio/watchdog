import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, vi, beforeEach } from "vitest";

vi.mock("../../api", () => ({
  listApiKeys: vi.fn(),
  getCurrentUser: vi.fn(),
  deleteApiKey: vi.fn(),
  replaceApiKeyShares: vi.fn(),
  getUsers: vi.fn(),
  getGroups: vi.fn(),
}));

const toastMock = { success: vi.fn(), error: vi.fn() };
vi.mock("../../contexts/ToastContext", () => ({ useToast: () => toastMock }));


let currentUser = { id: "u2", username: "me", api_keys: [] };
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: currentUser,
    hasPermission: () => true,
    updateUser: vi.fn(),
  }),
}));

import * as api from "../../api";
import ApiKeyPage from "../ApiKeyPage";

const sharedKey = {
  id: "k-shared",
  name: "Shared Key",
  key: "org-shared",
  otlp_token: null,
  owner_user_id: "owner-1",
  owner_username: "alice",
  is_shared: true,
  can_use: true,
  shared_with: [],
  is_default: false,
  is_enabled: true,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: null,
};

const ownedKey = {
  id: "k-owned",
  name: "Owned Key",
  key: "org-owned",
  otlp_token: "bo_test_token",
  owner_user_id: "u2",
  owner_username: "me",
  is_shared: false,
  can_use: true,
  shared_with: [],
  is_default: false,
  is_enabled: false,
  created_at: "2025-01-02T00:00:00Z",
  updated_at: null,
};

const defaultOwnedKey = {
  ...ownedKey,
  id: "k-default",
  name: "Default Owned Key",
  is_default: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getCurrentUser).mockImplementation(async () => ({
    ...currentUser,
    org_id: currentUser.api_keys?.find((k) => k.is_default)?.key || "org-default",
  }));
  vi.mocked(api.listApiKeys).mockImplementation(async () => currentUser.api_keys || []);
});

describe("ApiKeyPage (shared-key UX)", () => {
  it("shows owner username for a shared key", async () => {
    
    vi.mocked(api.listApiKeys).mockResolvedValue([sharedKey]);

    
    currentUser.api_keys = [sharedKey];
    const Page = (await import("../ApiKeyPage")).default;

    render(<Page />);

    expect(await screen.findByText(/Shared by alice/i)).toBeInTheDocument();
  });

  it("disables Generate Agent YAML when active key is shared", async () => {
    vi.mocked(api.listApiKeys).mockResolvedValue([sharedKey]);
    currentUser.api_keys = [sharedKey];
    const Page = (await import("../ApiKeyPage")).default;

    render(<Page />);

    const btn = await screen.findByRole("button", {
      name: /Generate Agent YAML/i,
    });
    expect(btn).toBeDisabled();
  });

  it("shows permission-specific toast when delete returns 403", async () => {
    
    vi.mocked(api.listApiKeys).mockResolvedValue([sharedKey]);
    vi.mocked(api.deleteApiKey).mockRejectedValue(
      Object.assign(new Error("Forbidden"), {
        status: 403,
        body: { detail: "Not authorized" },
      }),
    );

    currentUser.api_keys = [sharedKey];
    const Page = (await import("../ApiKeyPage")).default;

    render(<Page />);

    
    const rowDelete = await screen.findByRole("button", {
      name: `Delete ${sharedKey.name}`,
    });
    fireEvent.click(rowDelete);

    
    const dialog = await screen.findByRole("dialog");
    const { within } = await import("@testing-library/react");
    const confirmBtn = within(dialog).getByRole("button", { name: "Delete" });
    fireEvent.click(confirmBtn);

    await waitFor(() =>
      expect(toastMock.error).toHaveBeenCalledWith(
        "You are not authorized to delete this key",
      ),
    );
  });

  it("only allows YAML generation for owned keys", async () => {
    currentUser.api_keys = [{ ...sharedKey, is_enabled: true }, ownedKey];
    const Page = (await import("../ApiKeyPage")).default;

    render(<Page />);

    const btn = await screen.findByRole("button", {
      name: /Generate Agent YAML/i,
    });
    expect(btn).toBeEnabled();
    fireEvent.click(btn);

    const dialog = await screen.findByRole("dialog");
    const { within } = await import("@testing-library/react");
    expect(
      within(dialog).queryByRole("option", { name: /Shared Key/i }),
    ).not.toBeInTheDocument();
    expect(
      within(dialog).getByRole("option", { name: /Owned Key/i }),
    ).toBeInTheDocument();
  });

  it("does not render Share action for default keys", async () => {
    currentUser.api_keys = [defaultOwnedKey];
    const Page = (await import("../ApiKeyPage")).default;

    render(<Page />);

    expect(
      screen.queryByRole("button", { name: `Share ${defaultOwnedKey.name}` }),
    ).not.toBeInTheDocument();
  });
});
