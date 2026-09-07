import { createHash } from "node:crypto";

import { z } from "zod";

import { openApiActionPaths, openApiResourceKeys, openApiRouteOperations } from "./openapi-catalog";

export const PUBLIC_OPERATIONS = ["list", "read", "create", "update", "delete"] as const;
export type PublicOperation = typeof PUBLIC_OPERATIONS[number];

const permissionRuleSchema = z.object({
  module: z.string().min(1),
  resource: z.string().min(1),
  operations: z.array(z.enum(PUBLIC_OPERATIONS)),
  fields: z.array(z.string().min(1)).optional(),
  scope: z.record(z.string().min(1), z.array(z.string().min(1))).optional(),
}).strict();

const entitlementSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  larkGroupIds: z.array(z.string().min(1)).min(1),
  rules: z.array(permissionRuleSchema),
}).strict();

export const accessPolicySchema = z.object({
  schemaVersion: z.literal(1),
  requiredAccessGroupId: z.string().min(1),
  entitlements: z.array(entitlementSchema).min(1),
}).strict();

export type AccessPolicy = z.infer<typeof accessPolicySchema>;
export type PermissionRule = z.infer<typeof permissionRuleSchema>;
export type AccessEntitlement = z.infer<typeof entitlementSchema>;

const legacyOperationMap: Record<string, PublicOperation> = {
  submit: "update",
  reconcile: "update",
  unreconcile: "update",
  cancel: "delete",
};

function normalizeLegacyOperations(value: unknown): unknown {
  if (!value || typeof value !== "object" || Array.isArray(value)) return value;
  const source = value as Record<string, unknown>;
  if (!Array.isArray(source.entitlements)) return value;
  return {
    ...source,
    entitlements: source.entitlements.map((item) => {
      if (!item || typeof item !== "object" || Array.isArray(item)) return item;
      const entitlement = item as Record<string, unknown>;
      if (!Array.isArray(entitlement.rules)) return item;
      return {
        id: entitlement.id,
        label: entitlement.label,
        larkGroupIds: entitlement.larkGroupIds,
        rules: entitlement.rules.map((rule) => {
          if (!rule || typeof rule !== "object" || Array.isArray(rule)) return rule;
          const current = rule as Record<string, unknown>;
          if (!Array.isArray(current.operations)) return rule;
          return {
            ...current,
            operations: [...new Set(current.operations.map((operation) => typeof operation === "string" ? legacyOperationMap[operation] ?? operation : operation))],
          };
        }),
      };
    }),
  };
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value as Record<string, unknown>).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson((value as Record<string, unknown>)[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function parseAccessPolicy(value: unknown): AccessPolicy {
  // Read compatibility for policies created before CRUD-only capabilities.
  // New writes are still validated and persisted with only five operations.
  return accessPolicySchema.parse(normalizeLegacyOperations(value));
}

export function policyHash(policy: AccessPolicy): string {
  return createHash("sha256")
    .update(canonicalJson(policy))
    .digest("hex");
}

export function entitlementsForGroups(policy: AccessPolicy, groupIds: readonly string[]): string[] {
  const groups = new Set(groupIds);
  return policy.entitlements
    .filter((entitlement) => entitlement.larkGroupIds.some((groupId) => groups.has(groupId)))
    .map((entitlement) => entitlement.id);
}

export function policyRolesForGroups(policy: AccessPolicy, groupIds: readonly string[]): string[] {
  const groups = new Set(groupIds);
  return [...new Set(policy.entitlements
    .filter((entitlement) => entitlement.larkGroupIds.some((groupId) => groups.has(groupId)))
    .map((entitlement) => `Letron Policy - ${entitlement.id}`))].sort();
}

export function canAccessPolicy(
  policy: AccessPolicy,
  groupIds: readonly string[],
  input: { module: string; resource: string; operation: PublicOperation },
): boolean {
  const groups = new Set(groupIds);
  if (!groups.has(policy.requiredAccessGroupId)) return false;
  return policy.entitlements.some((entitlement) =>
    entitlement.larkGroupIds.some((groupId) => groups.has(groupId)) &&
    entitlement.rules.some((rule) =>
      rule.module === input.module && rule.resource === input.resource && rule.operations.includes(input.operation),
    ),
  );
}

export function visiblePolicyFeatures(policy: AccessPolicy, groupIds: readonly string[]): string[] {
  const features = [
    ["workspace", "erp", "workspace"],
    ["finance", "accounts", "purchase-invoices"],
    ["purchasing", "buying", "purchase-orders"],
    ["inventory", "stock", "items"],
    ["sales", "selling", "sales-orders"],
  ] as const;
  return features
    .filter(([, module, resource]) =>
      canAccessPolicy(policy, groupIds, { module, resource, operation: "list" }) ||
      canAccessPolicy(policy, groupIds, { module, resource, operation: "read" }),
    )
    .map(([id]) => id);
}

export function validatePolicy(value: unknown): { policy: AccessPolicy; sha256: string } {
  const policy = parseAccessPolicy(value);
  const groupOwners = new Set<string>();
  for (const entitlement of policy.entitlements) {
    if (groupOwners.has(entitlement.id)) throw new Error(`Duplicate entitlement: ${entitlement.id}`);
    groupOwners.add(entitlement.id);
    if (!/^group-[a-z0-9-]+$/.test(entitlement.id)) throw new Error("Each role must be derived from a Lark User Group");
  }
  if (!policy.entitlements.some((item) => item.larkGroupIds.includes(policy.requiredAccessGroupId))) {
    throw new Error("requiredAccessGroupId must be assigned to an entitlement");
  }
  return { policy, sha256: policyHash(policy) };
}

export function routeOperation(
  method: string,
  path: string,
): { module: string; resource: string; operation: PublicOperation } | null {
  const pathParts = path.replace(/^\/+|\/+$/g, "").split("/");
  const matches = (pattern: string) => {
    const patternParts = pattern.replace(/^\/+|\/+$/g, "").split("/");
    return patternParts.length === pathParts.length && patternParts.every((part, index) => part.startsWith("{") || part === pathParts[index]);
  };
  const custom = openApiRouteOperations().find((route) => route.method === method.toUpperCase() && matches(route.path));
  if (custom) return { module: custom.module, resource: custom.resource, operation: custom.operation };
  const parts = path.replace(/^\/+|\/+$/g, "").split("/");
  if (parts.length < 3 || parts[0] !== "api" || parts[1] !== "v1") return null;
  const moduleName = parts[2];
  const resource = parts[3];
  if (!moduleName || !resource) return null;
  if (!openApiResourceKeys().has(`${moduleName}/${resource}`)) return null;
  const actionKey = parts.length >= 6 ? `${moduleName}/${resource}/${parts[5]}` : "";
  if (parts.length === 6 && openApiActionPaths().has(actionKey) && ["submit", "reconcile", "unreconcile"].includes(parts[5])) {
    return { module: moduleName, resource, operation: "update" };
  }
  if (parts.length === 6 && openApiActionPaths().has(actionKey) && parts[5] === "cancel") {
    return { module: moduleName, resource, operation: "delete" };
  }
  if (parts.length > 5) return null;
  if (method === "GET") return { module: moduleName, resource, operation: parts.length === 4 ? "list" : "read" };
  if (method === "POST" && parts.length === 4) return { module: moduleName, resource, operation: "create" };
  if (["PUT", "PATCH"].includes(method) && parts.length === 5) return { module: moduleName, resource, operation: "update" };
  if (method === "DELETE" && parts.length === 5) return { module: moduleName, resource, operation: "delete" };
  return null;
}
