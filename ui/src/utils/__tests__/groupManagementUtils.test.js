import { describe, expect, it } from "vitest";
import {
  filterGroups,
  getCategoryDescription,
  groupPermissionsByResource,
  sortUsersByDisplayName,
} from "../groupManagementUtils";

describe("groupManagementUtils", () => {
  it("returns category descriptions with fallback", () => {
    expect(getCategoryDescription("users")).toContain("user permissions");
    expect(getCategoryDescription("custom")).toContain("custom permissions");
  });

  it("groups permissions by resource type", () => {
    const grouped = groupPermissionsByResource([
      { name: "read:users", resource_type: "users" },
      { name: "read:groups", resource_type: "groups" },
      { name: "write:users", resource_type: "users" },
    ]);
    expect(grouped.users).toHaveLength(2);
    expect(grouped.groups).toHaveLength(1);
  });

  it("filters groups and sorts users by display name", () => {
    const groups = [
      { name: "Platform", description: "Core team" },
      { name: "Security", description: "SOC" },
    ];
    expect(filterGroups(groups, "plat")).toHaveLength(1);

    const users = [
      { username: "zed" },
      { full_name: "Alice Doe", username: "alice" },
      { full_name: "Bob Doe", username: "bob" },
    ];
    const sorted = sortUsersByDisplayName(users);
    expect(sorted[0].full_name).toBe("Alice Doe");
  });
});
