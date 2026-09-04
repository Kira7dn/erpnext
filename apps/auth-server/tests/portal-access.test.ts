import { describe, expect, it } from "vitest";

import {
  hasErpAccess,
  parseLarkRoleMapping,
  rolesForLarkGroups,
  visibleErpFeatures,
} from "../src/server/portal-access";

const mapping = parseLarkRoleMapping(JSON.stringify({
  access: ["Desk User"],
  finance: ["Accounts User"],
  financeManager: ["Accounts User", "Accounts Manager"],
  stock: ["Stock User"],
}));

describe("portal role visibility", () => {
  it("unions roles from every matching Lark group", () => {
    expect([...rolesForLarkGroups(["access", "finance", "stock"], mapping)].sort()).toEqual([
      "Accounts User",
      "Desk User",
      "Stock User",
    ]);
  });

  it("ignores groups that do not have a configured ERP role mapping", () => {
    expect([...rolesForLarkGroups(["access", "unrelated"], mapping)]).toEqual(["Desk User"]);
  });

  it("shows ERP only when Desk User is derived from membership", () => {
    expect(hasErpAccess(rolesForLarkGroups(["access"], mapping))).toBe(true);
    expect(hasErpAccess(rolesForLarkGroups(["finance"], mapping))).toBe(false);
  });

  it("shows only features allowed by the derived roles", () => {
    const roles = rolesForLarkGroups(["access", "financeManager"], mapping);
    expect(visibleErpFeatures(roles).map((feature) => feature.id)).toEqual(["workspace", "finance"]);
  });

  it("rejects malformed role mappings", () => {
    expect(() => parseLarkRoleMapping("not-json")).toThrow(/valid JSON/);
    expect(() => parseLarkRoleMapping('{"access":[]}')).toThrow(/non-empty ERP role arrays/);
  });
});
