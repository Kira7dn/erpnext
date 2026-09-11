import "server-only";

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

type SupplierPortalConfig = {
  erp_base_url: string;
  next_internal_base_url: string;
  portal_public_base_url: string;
  auth_base_url: string;
  approval_submitter_email: string;
  deadline_interval_minutes: number;
};

function assertProductionPublicBaseUrl(value: string): void {
  if (process.env.NODE_ENV !== "production") return;
  let url: URL;
  try { url = new URL(value); }
  catch { throw new Error("Supplier Portal public URL must be a valid URL in production"); }
  if (url.protocol !== "https:" || /localhost|127\.0\.0\.1|host\.docker\.internal/i.test(url.hostname)) {
    throw new Error("Supplier Portal public URL must be HTTPS and externally reachable in production");
  }
}

function requiredString(source: Record<string, unknown>, key: string): string {
  const value = source[key];
  if (typeof value !== "string" || !value.trim()) throw new Error(`SUPPLIER_PORTAL_CONFIG_${key.toUpperCase()}_MISSING`);
  return value.trim();
}

function requiredPositiveNumber(source: Record<string, unknown>, key: string): number {
  const value = Number(source[key]);
  if (!Number.isFinite(value) || value <= 0) throw new Error(`SUPPLIER_PORTAL_CONFIG_${key.toUpperCase()}_INVALID`);
  return value;
}

export function supplierPortalConfig(): SupplierPortalConfig {
  const candidates = [
    process.env.LETRON_CONFIG_DIR ? join(process.env.LETRON_CONFIG_DIR, "supplier_portal.json") : "",
    join(process.cwd(), "config", "supplier_portal.json"),
    join(process.cwd(), "..", "..", "config", "supplier_portal.json"),
  ].filter(Boolean);
  const path = candidates.find((candidate) => existsSync(candidate));
  if (!path) throw new Error("SUPPLIER_PORTAL_CONFIG_NOT_FOUND");
  let source: Record<string, unknown>;
  try {
    source = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
  } catch {
    throw new Error("SUPPLIER_PORTAL_CONFIG_INVALID");
  }
  const erpBaseUrl = process.env.FRAPPE_ERP_NEXT_URL || requiredString(source, "erp_base_url");
  const portalBaseUrl = process.env.LETRON_ERP_APP_BASE_URL || requiredString(source, "portal_public_base_url");
  const config = {
    erp_base_url: erpBaseUrl,
    next_internal_base_url: portalBaseUrl,
    portal_public_base_url: portalBaseUrl,
    auth_base_url: process.env.LETRON_AUTH_BASE_URL || requiredString(source, "auth_base_url"),
    approval_submitter_email: requiredString(source, "approval_submitter_email"),
    deadline_interval_minutes: requiredPositiveNumber(source, "deadline_interval_minutes"),
  } satisfies SupplierPortalConfig;
  assertProductionPublicBaseUrl(config.portal_public_base_url);
  return config;
}
