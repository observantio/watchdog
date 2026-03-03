import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, vi, beforeEach } from "vitest";


vi.mock("../../api", () => ({
  getNotificationChannels: vi.fn(),
  deleteNotificationChannel: vi.fn(),
  getAllowedChannelTypes: vi.fn(),
  listJiraIntegrations: vi.fn(),
  getAuthMode: vi.fn(),
  
  createNotificationChannel: vi.fn(),
  updateNotificationChannel: vi.fn(),
  testNotificationChannel: vi.fn(),
  createJiraIntegration: vi.fn(),
  updateJiraIntegration: vi.fn(),
  deleteJiraIntegration: vi.fn(),
}));

const toastMock = { success: vi.fn(), error: vi.fn() };
vi.mock("../../contexts/ToastContext", () => ({ useToast: () => toastMock }));

let currentUser = { id: "u1" };
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: currentUser, hasPermission: () => true }),
}));

import * as api from "../../api";
import IntegrationsPage from "../IntegrationsPage";

const exampleChannel = {
  id: "c1",
  name: "ADMIN",
  type: "email",
  visibility: "private",
  createdBy: "u1",
  enabled: true,
  config: { url: "https://example" },
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("IntegrationsPage deletion flow", () => {
  const setupCommonMocks = (deleteResult) => {
    vi.mocked(api.getNotificationChannels).mockResolvedValue([exampleChannel]);
    vi.mocked(api.getAllowedChannelTypes).mockResolvedValue({
      allowedTypes: [],
    });
    vi.mocked(api.listJiraIntegrations).mockResolvedValue({ items: [] });
    vi.mocked(api.getAuthMode).mockResolvedValue({ oidc_enabled: false });
    if (deleteResult instanceof Error) {
      vi.mocked(api.deleteNotificationChannel).mockRejectedValue(deleteResult);
    } else {
      vi.mocked(api.deleteNotificationChannel).mockResolvedValue();
    }
  };

  it("closes confirm dialog when channel is deleted successfully", async () => {
    setupCommonMocks();

    render(<IntegrationsPage />);

    
    expect(await screen.findByText("ADMIN")).toBeInTheDocument();

    
    const rowDelete = screen.getByRole("button", { name: /Delete channel/i });
    fireEvent.click(rowDelete);

    const dialog = await screen.findByRole("dialog");
    const { within } = await import("@testing-library/react");
    const confirmBtn = within(dialog).getByRole("button", { name: "Delete" });
    fireEvent.click(confirmBtn);

    
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(api.deleteNotificationChannel).toHaveBeenCalledWith("c1");
  });

  it("reopens confirmation if delete API fails", async () => {
    setupCommonMocks(new Error("failure"));

    render(<IntegrationsPage />);
    expect(await screen.findByText("ADMIN")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Delete channel/i }));
    const dialog = await screen.findByRole("dialog");
    const { within } = await import("@testing-library/react");
    const confirmBtn = within(dialog).getByRole("button", { name: "Delete" });
    fireEvent.click(confirmBtn);

    
    await waitFor(() =>
      expect(api.deleteNotificationChannel).toHaveBeenCalledWith("c1"),
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
