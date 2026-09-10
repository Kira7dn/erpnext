import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

type SupplierPortalConfig = {
  next_internal_base_url: string;
  portal_public_base_url: string;
  auth_base_url: string;
  approval_submitter_email: string;
};

function publicBaseUrlFromEnvironment(): string | undefined {
  const value = process.env.LETRON_SUPPLIER_PORTAL_PUBLIC_BASE_URL;
  return typeof value === "string" && value.trim() ? value.trim().replace(/\/$/, "") : undefined;
}

function assertProductionPublicBaseUrl(value: string): void {
  if (process.env.NODE_ENV !== "production") return;
  let url: URL;
  try { url = new URL(value); }
  catch { throw new Error("LETRON_SUPPLIER_PORTAL_PUBLIC_BASE_URL must be a valid URL in production"); }
  if (url.protocol !== "https:" || /localhost|127\.0\.0\.1|host\.docker\.internal/i.test(url.hostname)) {
    throw new Error("Supplier Portal public URL must be HTTPS and externally reachable in production");
  }
}

function requiredString(source: Record<string, unknown>, key: string): string {
  const value = source[key];
  if (typeof value !== "string" || !value.trim()) throw new Error(`SUPPLIER_PORTAL_CONFIG_${key.toUpperCase()}_MISSING`);
  return value.trim();
}

export function supplierPortalConfig(): SupplierPortalConfig {
  const paths = [
    process.env.LETRON_CONFIG_DIR ? join(process.env.LETRON_CONFIG_DIR, "supplier_portal.json") : "",
    join(process.cwd(), "config", "supplier_portal.json"),
    join(process.cwd(), "..", "..", "config", "supplier_portal.json"),
  ].filter(Boolean);
  const path = paths.find((candidate) => existsSync(candidate));
  if (!path) throw new Error("SUPPLIER_PORTAL_CONFIG_NOT_FOUND");
  let source: Record<string, unknown>;
  try {
    source = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
  } catch {
    throw new Error("SUPPLIER_PORTAL_CONFIG_INVALID");
  }
  const config = {
    next_internal_base_url: process.env.LETRON_NEXT_BASE_URL || requiredString(source, "next_internal_base_url"),
    portal_public_base_url: publicBaseUrlFromEnvironment() || requiredString(source, "portal_public_base_url"),
    auth_base_url: process.env.LETRON_AUTH_BASE_URL || requiredString(source, "auth_base_url"),
    approval_submitter_email: requiredString(source, "approval_submitter_email"),
  } satisfies SupplierPortalConfig;
  assertProductionPublicBaseUrl(config.portal_public_base_url);
  return config;
}
