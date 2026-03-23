import { fireEvent, render, screen } from "@testing-library/react";
import { vi, describe, it, beforeEach, expect } from "vitest";
import { useAuth } from "../../../contexts/AuthContext";

vi.mock("../../ui", () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: (props) => <input {...props} />,
  Textarea: (props) => <textarea {...props} />,
  Select: ({ children, onChange, ...props }) => (
    <select {...props} onChange={onChange}>
      {children}
    </select>
  ),
}));
vi.mock("../../HelpTooltip", () => ({ default: () => <span /> }));
vi.mock("../../../contexts/AuthContext", () => ({
  useAuth: vi.fn(() => ({ hasPermission: vi.fn(), user: null })),
}));

import RuleEditor from "../RuleEditor";
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

// new tests for API key selection behaviour

describe("RuleEditor API key selector", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const apiKeys = [
    { id: "1", key: "default", name: "Default", is_default: true, is_enabled: true },
    { id: "2", key: "ubuntu", name: "ubuntu", is_default: false, is_enabled: true },
  ];

  it("starts with auto scope active and individual options disabled", () => {
    useAuth.mockReturnValue({ hasPermission: () => true, user: { id: "u-1" } });
    render(<RuleEditor {...defaultProps} apiKeys={apiKeys} />);

    const autoBtn = screen.getByRole("button", { name: /auto scope/i });
    expect(autoBtn).toBeInTheDocument();
    const autoCheckbox = autoBtn.querySelector("input[type=checkbox]");
    expect(autoCheckbox).toBeChecked();

    const defaultBtn = screen.getByRole("button", { name: /default/i });
    expect(defaultBtn).toBeDisabled();
    const ubuntuBtn = screen.getByRole("button", { name: /ubuntu/i });
    expect(ubuntuBtn).toBeDisabled();
  });

  it("can toggle an explicit key then return to auto when deselected", () => {
    useAuth.mockReturnValue({ hasPermission: () => true, user: { id: "u-1" } });
    render(<RuleEditor {...defaultProps} apiKeys={apiKeys} />);

    const autoBtn = screen.getByRole("button", { name: /auto scope/i });
    let ubuntuBtn = screen.getByRole("button", { name: /ubuntu/i });

    // Leave auto mode first; explicit scopes are disabled while auto is active.
    fireEvent.click(autoBtn);
    expect(autoBtn.querySelector("input")).not.toBeChecked();
    expect(ubuntuBtn).not.toBeDisabled();

    fireEvent.click(ubuntuBtn);
    ubuntuBtn = screen.getByRole("button", { name: /ubuntu/i });
    expect(ubuntuBtn.querySelector("input")).toBeChecked();
    expect(autoBtn.querySelector("input")).not.toBeChecked();

    fireEvent.click(ubuntuBtn);
    ubuntuBtn = screen.getByRole("button", { name: /ubuntu/i });
    expect(autoBtn.querySelector("input")).toBeChecked();
    expect(ubuntuBtn.querySelector("input")).not.toBeChecked();
  });

  it("shows owner-key visibility hint for non-owner when scope is auto/unknown", () => {
    useAuth.mockReturnValue({ hasPermission: () => true, user: { id: "viewer-1" } });
    render(
      <RuleEditor
        {...defaultProps}
        apiKeys={apiKeys}
        rule={{ ...baseRule, createdBy: "owner-1", orgId: "" }}
      />,
    );

    expect(
      screen.getByText(/api key selected for this rule has not been shared/i),
    ).toBeInTheDocument();
  });

  it("shows owner-key visibility hint for non-owner when selected scope is not visible", () => {
    useAuth.mockReturnValue({ hasPermission: () => true, user: { id: "viewer-1" } });
    render(
      <RuleEditor
        {...defaultProps}
        apiKeys={apiKeys}
        rule={{ ...baseRule, createdBy: "owner-1", orgId: "unshared-scope-id" }}
      />,
    );

    expect(
      screen.getByText(/api key selected for this rule has not been shared/i),
    ).toBeInTheDocument();
  });
});

// correlation id generator

describe("RuleEditor correlation ID generator", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("switches to custom mode and fills generated value", () => {
    useAuth.mockReturnValue({ hasPermission: () => true });
    render(
      <RuleEditor
        {...defaultProps}
        apiKeys={[]}
        rule={{ ...baseRule, group: "custom-seed" }}
      />,
    );

    // Correlation UI is in Alert Condition step.
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));

    const input = screen.getByPlaceholderText("default");
    expect(input).toBeInTheDocument();
    expect(input.value).toBe("custom-seed");

    const genBtn = screen.getByTitle(/Generate random ID/i);
    fireEvent.click(genBtn);
    expect(input.value).toMatch(/^[0-9a-zA-Z]+$/);
    expect(input.value).toHaveLength(10);
    const first = input.value;
    fireEvent.click(genBtn);
    expect(input.value).not.toBe(first);
    expect(input.value).toHaveLength(10);
  });
});
