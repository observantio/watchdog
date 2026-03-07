import React from "react";
import { render, fireEvent, waitFor, screen } from "@testing-library/react";
import { vi, describe, it, beforeEach, expect } from "vitest";

vi.mock("../../components/ui", () => ({
  Card: ({ children }) => <div>{children}</div>,
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Select: ({ children, onChange, ...props }) => (
    <select {...props} onChange={(e) => onChange?.(e.target.value)}>
      {children}
    </select>
  ),
  Badge: ({ children }) => <span>{children}</span>,
  Spinner: () => <div>Loading</div>,
  Modal: ({ children, isOpen }) => (isOpen ? <div>{children}</div> : null),
  Input: (props) => <input {...props} />,
  Alert: ({ children }) => <div>{children}</div>,
}));
vi.mock("../../components/HelpTooltip", () => ({ default: () => <span /> }));
vi.mock("../../components/ui/PageHeader", () => ({
  default: ({ children }) => <div>{children}</div>,
}));
const toastFns = { success: vi.fn(), error: vi.fn() };
vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => toastFns,
}));
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "u2", username: "alice" },
    hasPermission: () => true,
  }),
}));

vi.mock("../../api", () => ({
  getIncidents: vi.fn(),
  updateIncident: vi.fn(),
  getUsers: vi.fn(),
  getGroups: vi.fn(),
  listJiraIntegrations: vi.fn(),
  listJiraProjectsByIntegration: vi.fn(),
  listJiraIssueTypes: vi.fn(),
  listIncidentJiraComments: vi.fn(),
  createIncidentJira: vi.fn(),
  createIncidentJiraComment: vi.fn(),
  syncIncidentJiraComments: vi.fn(),
  getAlertsByFilter: vi.fn(),
}));

import IncidentBoardPage, { clearDroppedState } from "../IncidentBoardPage";
import * as api from "../../api";

describe("clearDroppedState", () => {
  it("removes dropped id key when id is defined", () => {
    const prev = { a: true, b: true };
    const next = clearDroppedState(prev, "a");

    expect(next).toEqual({ b: true });
    expect(prev).toEqual({ a: true, b: true });
  });

  it("returns previous state when dropped id is undefined", () => {
    const prev = { a: true };
    const next = clearDroppedState(prev, undefined);

    expect(next).toBe(prev);
  });

  it("returns previous state when dropped id is empty", () => {
    const prev = { a: true };
    const next = clearDroppedState(prev, "");

    expect(next).toBe(prev);
  });
});

describe("IncidentBoardPage — UI refresh & persistence", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("refreshes incidents after saving assignment (no reload needed)", async () => {
    const initial = {
      id: "i1",
      alertName: "Alert 1",
      status: "open",
      assignee: "",
      fingerprint: "f1",
      lastSeenAt: new Date().toISOString(),
      severity: "warning",
      notes: [],
    };
    const updated = { ...initial, assignee: "u2" };
    const user = {
      id: "u2",
      username: "alice",
      email: "alice@example.com",
      full_name: "Alice Example",
    };

    api.getIncidents
      .mockResolvedValueOnce([initial])
      .mockResolvedValue([updated]);
    api.getUsers.mockResolvedValue([user]);
    api.getGroups.mockResolvedValue([]);
    api.updateIncident.mockResolvedValue(updated);

    const { getByText, findByText, getByTitle } = render(<IncidentBoardPage />);

    await findByText("Alert 1");

    fireEvent.click(getByTitle("View notes"));
    
    fireEvent.click(getByText("Assignment"));
    fireEvent.click(getByText("Assign to me"));
    fireEvent.click(getByText("Save changes"));

    await waitFor(() =>
      expect(api.updateIncident).toHaveBeenCalledWith(
        "i1",
        expect.objectContaining({ assignee: "u2" }),
      ),
    );
    await waitFor(() =>
      expect(api.getIncidents.mock.calls.length).toBeGreaterThanOrEqual(2),
    );
    
    await waitFor(() => expect(screen.getByText(/Alice Example/)).toBeTruthy());
  });

  it("renders note text with IDs replaced by user labels", async () => {
    
    const noteId = "123e4567-e89b-12d3-a456-426614174000";
    const initial = {
      id: "i1",
      alertName: "Alert 1",
      status: "open",
      assignee: "",
      fingerprint: "f1",
      lastSeenAt: new Date().toISOString(),
      severity: "warning",
      notes: [
        {
          author: "admin",
          text: `Assigned to ${noteId} by admin`,
          createdAt: new Date().toISOString(),
        },
      ],
    };
    api.getIncidents.mockResolvedValue([initial]);
    api.getUsers.mockResolvedValue([{ id: noteId, username: "bob" }]);
    api.getGroups.mockResolvedValue([]);

    const { findByText } = render(<IncidentBoardPage />);
    await findByText("Alert 1");
    fireEvent.click(screen.getByTitle("View notes"));
    
    await waitFor(() =>
      expect(screen.queryByText(noteId)).not.toBeInTheDocument(),
    );
    expect(screen.getByText(/bob/)).toBeInTheDocument();
  });

  it("persists visibility tab and selected group to localStorage", async () => {
    api.getIncidents.mockResolvedValue([]);
    api.getUsers.mockResolvedValue([]);
    api.getGroups.mockResolvedValue([{ id: "g1", name: "Team A" }]);

    const { getByText, findByText, findByRole } = render(<IncidentBoardPage />);

    await findByText("Public");

    fireEvent.click(getByText("Group"));

    const select = await findByRole("combobox");
    fireEvent.change(select, { target: { value: "g1" } });

    expect(localStorage.getItem("incidents-visibility")).toEqual(
      JSON.stringify("group"),
    );
    expect(localStorage.getItem("incidents-selected-group")).toEqual(
      JSON.stringify("g1"),
    );
  });

  it("blocks resolving when underlying alert is still active", async () => {
    const initial = {
      id: "i1",
      alertName: "Alert 1",
      status: "assigned",
      assignee: "u2",
      fingerprint: "f1",
      lastSeenAt: new Date().toISOString(),
      severity: "warning",
      notes: [],
    };
    api.getIncidents.mockResolvedValue([initial]);
    api.getUsers.mockResolvedValue([]);
    api.getGroups.mockResolvedValue([]);
    api.getAlertsByFilter.mockResolvedValue([{ id: "a1" }]);
    api.updateIncident.mockResolvedValue({});

    const { findByText, findByTitle } = render(<IncidentBoardPage />);

    await findByText("Alert 1");
    fireEvent.click(await findByTitle("Quick resolve"));

    await waitFor(() =>
      expect(api.getAlertsByFilter).toHaveBeenCalledWith(
        { fingerprint: "f1" },
        true,
      ),
    );

    // error body should show extended message
    expect(
      screen.getByText(/Wait a few minutes since this will take some time/i),
    ).toBeTruthy();

    // toast should show short message
    expect(toastFns.error).toHaveBeenCalledWith(
      "Alert still active. Resolve it first.",
    );
  });

  it("renders create jira integration link with proper href when jira tab opened without integrations", async () => {
    const initial = {
      id: "i1",
      alertName: "Alert 1",
      status: "open",
      assignee: "",
      fingerprint: "f1",
      lastSeenAt: new Date().toISOString(),
      severity: "warning",
      notes: [],
    };
    api.getIncidents.mockResolvedValue([initial]);
    api.getUsers.mockResolvedValue([]);
    api.getGroups.mockResolvedValue([]);
    api.listJiraIntegrations.mockResolvedValue([]);

    const { findByText, getByText } = render(<IncidentBoardPage />);
    await findByText("Alert 1");

    
    fireEvent.click(screen.getByText("edit").closest("button"));
    await screen.findByRole("button", { name: /Details/i });

    const jiraTab = await screen.findByRole("button", { name: /Jira/i });
    fireEvent.click(jiraTab);

    const link = await screen.findByRole("link", {
      name: /Create Jira integration/i,
    });
    expect(link).toHaveAttribute("href", "/integrations");
  });

  it("shows quick unhide but no quick edit for hidden resolved cards", async () => {
    const hiddenResolved = {
      id: "i-hidden-1",
      alertName: "Hidden Resolved Alert",
      status: "resolved",
      assignee: "",
      fingerprint: "f-hidden-1",
      lastSeenAt: new Date().toISOString(),
      severity: "warning",
      notes: [],
      hideWhenResolved: true,
    };

    api.getIncidents.mockResolvedValue([hiddenResolved]);
    api.getUsers.mockResolvedValue([]);
    api.getGroups.mockResolvedValue([]);

    render(<IncidentBoardPage />);
    await screen.findByText("Hidden Resolved Alert");

    expect(screen.getByTitle("Unhide incident")).toBeInTheDocument();
    expect(screen.queryByText("edit")).not.toBeInTheDocument();
  });
});
