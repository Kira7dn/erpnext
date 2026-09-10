import "server-only";

import { readFileSync } from "node:fs";
import { join } from "node:path";

type SupplierPortalConfig = {
  erp_base_url: string;
  next_base_url: string;
  auth_base_url: string;
  approval_submitter_email: string;
  review_user: string;
  deadline_interval_minutes: number;
};

const defaults: SupplierPortalConfig = {
  erp_base_url: "http://localhost:8080",
  next_base_url: "http://localhost:3001",
  auth_base_url: "http://localhost:3000",
  approval_submitter_email: "leducanh@ledb.vn",
  review_user: "Administrator",
  deadline_interval_minutes: 5,
};

export function supplierPortalConfig(): SupplierPortalConfig {
  const candidates = [
    process.env.LETRON_CONFIG_DIR ? join(process.env.LETRON_CONFIG_DIR, "supplier_portal.json") : "",
    join(process.cwd(), "config", "supplier_portal.json"),
    join(process.cwd(), "..", "..", "config", "supplier_portal.json"),
  ].filter(Boolean);
  for (const path of candidates) {
    try { return { ...defaults, ...JSON.parse(readFileSync(path, "utf8")) } as SupplierPortalConfig; }
    catch { /* Try the next deployment location. */ }
  }
  return defaults;
}
