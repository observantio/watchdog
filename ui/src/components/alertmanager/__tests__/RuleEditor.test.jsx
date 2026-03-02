import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { vi, describe, it, beforeEach, expect } from "vitest";
import { useAuth } from "../../../contexts/AuthContext";

// basic UI components are mocked to avoid importing tailwind/etc
vi.mock("../../ui", () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: (props) => <input {...props} />,
  Select: ({ children, onChange, ...props }) => (
    <select {...props} onChange={(e) => onChange?.(e.target.value)}>
      {children}
    </select>
  ),
}));
vi.mock("../../HelpTooltip", () => ({ default: () => <span /> }));

// we will provide a fake AuthContext with configurable permission
vi.mock("../../../contexts/AuthContext", () => ({
  useAuth: vi.fn(() => ({ hasPermission: vi.fn() })),
}));

import RuleEditor from "../RuleEditor";

// minimal props
const noop = () => {};
const baseRule = {
  id: "rule-1",
  name: "CPU usage high",
  orgId: "",
  expr: "up == 0",
  duration: "1m",
  severity: "warning",
  labels: {},
  annotations: { summary: "CPU issue", description: "CPU issue details" },
  enabled: true,
  group: "default",
  notificationChannels: [],
  visibility: "private",
  sharedGroupIds: [],
};
const defaultProps = {
  rule: baseRule,
  apiKeys: [],
  onSave: noop,
  onCancel: noop,
};

const advanceToStep4 = () => {
  fireEvent.click(screen.getByRole("button", { name: /Next/i }));
  fireEvent.click(screen.getByRole("button", { name: /Next/i }));
  fireEvent.click(screen.getByRole("button", { name: /Next/i }));
};

describe("RuleEditor notification channel section", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('displays "No channels configured" message and manage link when user has read permission', () => {
    useAuth.mockReturnValue({ hasPermission: () => true });

    render(<RuleEditor {...defaultProps} channels={[]} />);
    advanceToStep4();

    expect(
      screen.getByRole("heading", { name: "No Channels Configured" }),
    ).toBeInTheDocument();
    const link = screen.getByText("Manage Integrations").closest("a");
    expect(link).toHaveAttribute("href", "/integrations");
  });

  it("shows permission warning when user lacks read:channels", () => {
    useAuth.mockReturnValue({ hasPermission: () => false });

    render(<RuleEditor {...defaultProps} channels={[]} />);
    advanceToStep4();

    expect(screen.getByText(/don't have permission/i)).toBeInTheDocument();
    expect(screen.queryByText("Manage Integrations")).not.toBeInTheDocument();
  });
});
