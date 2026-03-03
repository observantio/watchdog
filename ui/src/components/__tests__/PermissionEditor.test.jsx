import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import PermissionEditor from "../PermissionEditor";
import * as api from "../../api";
import { USER_ROLES } from "../../utils/constants";
import { ToastProvider } from "../../contexts/ToastContext";

vi.mock("../../api", () => ({
  getPermissions: vi.fn(),
  getRoleDefaults: vi.fn(),
  updateUserPermissions: vi.fn(),
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: "admin-1",
      role: "admin",
      permissions: ["manage:users"],
      is_superuser: false,
    },
  }),
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

    await waitFor(() => expect(api.getPermissions).toHaveBeenCalled());
    const roleSelect = screen.getByLabelText(/Role/i);
    expect(roleSelect).toBeInTheDocument();

    USER_ROLES.forEach((r) => {
      const opt = screen.getByRole("option", { name: r.label });
      expect(opt).toHaveValue(r.value);
    });
    expect(roleSelect).toHaveValue("user");
  });
});
