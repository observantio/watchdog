import React from "react";
import { render, waitFor, fireEvent } from "@testing-library/react";

// minimal mocks for dependencies
vi.mock("../../hooks", async () => {
  const actual = await vi.importActual("../../hooks");
  return { ...actual };
});
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ user: { api_keys: [] }, hasPermission: () => true }),
}));

vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => ({ toast: { success: vi.fn(), error: vi.fn() } }),
}));
vi.mock("../components/ui", () => ({
  Button: ({ children }) => <button>{children}</button>,
  ConfirmDialog: () => <div />,
}));
vi.mock("../components/ui/PageHeader", () => ({
  default: ({ children }) => <div>{children}</div>,
}));

import GrafanaPage from "../GrafanaPage";

vi.mock("../api", () => ({
  searchDashboards: vi.fn().mockResolvedValue([]),
  getDatasources: vi.fn().mockResolvedValue([]),
  getFolders: vi.fn().mockResolvedValue([]),
  getGroups: vi.fn().mockResolvedValue([]),
  getDashboardFilterMeta: vi.fn().mockResolvedValue({}),
  getDatasourceFilterMeta: vi.fn().mockResolvedValue({}),
  createGrafanaBootstrapSession: vi.fn().mockResolvedValue({}),
}));

describe("GrafanaPage state persistence", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("loads activeTab from localStorage", async () => {
    localStorage.setItem("grafana-active-tab", JSON.stringify("datasources"));
    const { getByRole } = render(<GrafanaPage />);
    // the Datasources button should have active styling
    const dsBtn = await waitFor(() =>
      getByRole("button", { name: /Datasources/i }),
    );
    expect(dsBtn).toHaveClass("text-sre-primary");
  });

  it("persists activeTab changes", async () => {
    const { getByRole } = render(<GrafanaPage />);
    // storage may start blank or with default dashboards
    const init = JSON.parse(localStorage.getItem("grafana-active-tab"));
    expect([null, "dashboards"]).toContain(init);
    // click the Folders tab to change
    const foldersBtn = getByRole("button", { name: /Folders/i });
    fireEvent.click(foldersBtn);
    expect(JSON.parse(localStorage.getItem("grafana-active-tab"))).toBe(
      "folders",
    );
  });
});
