import { z } from "zod";

const roleMappingSchema = z.record(
  z.string().min(1),
  z.array(z.string().min(1)).min(1),
);

export type LarkRoleMapping = z.infer<typeof roleMappingSchema>;

export type PortalFeature = {
  id: string;
  label: string;
  requiredRoles: readonly string[];
};

export const ERP_PORTAL_FEATURES: readonly PortalFeature[] = [
  { id: "workspace", label: "Không gian ERP", requiredRoles: ["Desk User"] },
  { id: "finance", label: "Tài chính", requiredRoles: ["Accounts User", "Accounts Manager"] },
  { id: "purchasing", label: "Mua hàng", requiredRoles: ["Purchase User", "Purchase Manager"] },
  { id: "inventory", label: "Kho", requiredRoles: ["Stock User", "Stock Manager"] },
  { id: "sales", label: "Bán hàng", requiredRoles: ["Sales User", "Sales Manager"] },
];

export function parseLarkRoleMapping(rawMapping: string): LarkRoleMapping {
  let value: unknown;
  try {
    value = JSON.parse(rawMapping);
  } catch {
    throw new Error("LETRON_SSO_LARK_ROLE_MAPPING must contain valid JSON");
  }

  const parsed = roleMappingSchema.safeParse(value);
  if (!parsed.success) {
    throw new Error("LETRON_SSO_LARK_ROLE_MAPPING must map group IDs to non-empty ERP role arrays");
  }
  return parsed.data;
}

export function rolesForLarkGroups(groupIds: readonly string[], mapping: LarkRoleMapping): Set<string> {
  return new Set(groupIds.flatMap((groupId) => mapping[groupId] ?? []));
}

export function hasErpAccess(roles: ReadonlySet<string>): boolean {
  return roles.has("Desk User");
}

export function visibleErpFeatures(
  roles: ReadonlySet<string>,
  features: readonly PortalFeature[] = ERP_PORTAL_FEATURES,
): PortalFeature[] {
  return features.filter((feature) => feature.requiredRoles.some((role) => roles.has(role)));
}
