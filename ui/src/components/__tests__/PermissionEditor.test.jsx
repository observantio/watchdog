import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import PermissionEditor from "../PermissionEditor";
import * as api from "../../api";
import { USER_ROLES } from "../../utils/constants";
import { ToastProvider } from "../../contexts/ToastContext";

// mock the API module methods used by PermissionEditor
vi.mock("../../api", () => ({
  getPermissions: vi.fn(),
  getRoleDefaults: vi.fn(),
  updateUserPermissions: vi.fn(),
}));

describe("PermissionEditor", () => {
  beforeEach(() => {
    api.getPermissions.mockResolvedValue([]);
    api.getRoleDefaults.mockResolvedValue({});
  });

  it("renders without crashing and shows role options from constants", async () => {
    const user = {
      id: "u1",
      username: "bob",
      role: "user",
      group_ids: [],
      direct_permissions: [],
    };
    // wrap component with toast provider because it uses useToast internally
    render(
      <ToastProvider>
        <PermissionEditor
          user={user}
          groups={[]}
          onClose={vi.fn()}
          onSave={vi.fn()}
        />
      </ToastProvider>,
    );

    // the component fetches permissions on mount, ensure that happens
    await waitFor(() => expect(api.getPermissions).toHaveBeenCalled());

    // confirm the dropdown exists and the expected options are present
    const roleSelect = screen.getByLabelText(/Role/i);
    expect(roleSelect).toBeInTheDocument();

    USER_ROLES.forEach((r) => {
      const opt = screen.getByRole("option", { name: r.label });
      expect(opt).toHaveValue(r.value);
    });

    // the select should default to the user's current role
    expect(roleSelect).toHaveValue("user");
  });
});
