import { describe, expect, it } from "vitest";

import {
  canAccessPolicy,
  policyRolesForGroups,
  parseAccessPolicy,
  policyHash,
  PUBLIC_OPERATIONS,
  routeOperation,
  validatePolicy,
  visiblePolicyFeatures,
} from "../src/server/access-policy";
import { openApiPermissions } from "../src/server/openapi-catalog";

const policy = parseAccessPolicy({
  schemaVersion: 1,
  requiredAccessGroupId: "access",
  entitlements: [
    {
      id: "group-finance",
      label: "Finance",
      larkGroupIds: ["finance"],
      rules: [{ module: "accounts", resource: "purchase-invoices", operations: ["list", "read", "create"] }],
    },
    {
      id: "group-access",
      label: "ERP Access",
      larkGroupIds: ["access"],
      rules: [{ module: "erp", resource: "workspace", operations: ["list"] }],
    },
  ],
});

describe("access policy", () => {
  it("uses only CRUD capabilities", () => {
    expect(PUBLIC_OPERATIONS).toEqual(["list", "read", "create", "update", "delete"]);
    expect(parseAccessPolicy({
      ...policy,
      entitlements: [{ ...policy.entitlements[0], rules: [{ ...policy.entitlements[0].rules[0], operations: ["submit"] }] }],
    }).entitlements[0].rules[0].operations).toEqual(["update"]);
  });

  it("normalizes every OpenAPI endpoint into a CRUD capability", () => {
    const permissions = openApiPermissions();
    expect(permissions.every((item) => PUBLIC_OPERATIONS.includes(item.operation as typeof PUBLIC_OPERATIONS[number]))).toBe(true);
    expect(new Set(permissions.map((item) => item.operation))).toEqual(new Set(["list", "read", "create", "update", "delete"]));
    expect(permissions.find((item) => item.module === "accounts" && item.resource === "bank-transactions" && item.operation === "update")).toBeDefined();
  });

  it("requires the access group and evaluates an operation", () => {
    expect(canAccessPolicy(policy, ["finance"], { module: "accounts", resource: "purchase-invoices", operation: "list" })).toBe(false);
    expect(canAccessPolicy(policy, ["access", "finance"], { module: "accounts", resource: "purchase-invoices", operation: "create" })).toBe(true);
    expect(canAccessPolicy(policy, ["access", "finance"], { module: "accounts", resource: "purchase-invoices", operation: "update" })).toBe(false);
  });

  it("limits decisions to registered public routes", () => {
    expect(routeOperation("GET", "/api/v1/accounts/purchase-invoices")).toEqual({ module: "accounts", resource: "purchase-invoices", operation: "list" });
    expect(routeOperation("POST", "/api/v1/accounts/purchase-invoices/PINV-1/submit")).toEqual({ module: "accounts", resource: "purchase-invoices", operation: "update" });
    expect(routeOperation("POST", "/api/v1/accounts/purchase-invoices/PINV-1/cancel")).toEqual({ module: "accounts", resource: "purchase-invoices", operation: "delete" });
    expect(routeOperation("POST", "/api/v1/accounts/bank-transactions/BT-1/reconcile")).toEqual({ module: "accounts", resource: "bank-transactions", operation: "update" });
    expect(routeOperation("POST", "/api/v1/accounts/bank-transactions/BT-1/unreconcile")).toEqual({ module: "accounts", resource: "bank-transactions", operation: "update" });
    expect(routeOperation("POST", "/api/v1/accounts/banks/BANK-1/submit")).toBeNull();
    expect(routeOperation("GET", "/api/resource/User")).toBeNull();
    expect(routeOperation("GET", "/api/v1/unknown/anything")).toBeNull();
  });

  it("derives portal features from the published policy", () => {
    expect(visiblePolicyFeatures(policy, ["access", "finance"])).toEqual(["workspace", "finance"]);
  });

  it("projects the union of managed ERP roles for matching groups", () => {
    expect(policyRolesForGroups(policy, ["access", "finance"])).toEqual([
      "Letron Policy - group-access",
      "Letron Policy - group-finance",
    ]);
  });

  it("rejects roles that are not derived from a Lark group", () => {
    expect(() => validatePolicy({
      ...policy,
      entitlements: [{ ...policy.entitlements[0], id: "finance" }],
    })).toThrow("derived from a Lark User Group");
  });

  it("hashes the canonical validated policy", () => {
    expect(policyHash(policy)).toMatch(/^[a-f0-9]{64}$/);
  });
});
