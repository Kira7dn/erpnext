import { readFileSync } from "node:fs";
import { join } from "node:path";

type SupplierPortalConfig = { next_base_url: string; auth_base_url: string; approval_submitter_email: string };
const defaults: SupplierPortalConfig = { next_base_url: "http://localhost:3001", auth_base_url: "http://localhost:3000", approval_submitter_email: "leducanh@ledb.vn" };

export function supplierPortalConfig(): SupplierPortalConfig {
  const paths = [process.env.LETRON_CONFIG_DIR ? join(process.env.LETRON_CONFIG_DIR, "supplier_portal.json") : "", join(process.cwd(), "config", "supplier_portal.json"), join(process.cwd(), "..", "..", "config", "supplier_portal.json")].filter(Boolean);
  for (const path of paths) {
    try { return { ...defaults, ...JSON.parse(readFileSync(path, "utf8")) } as SupplierPortalConfig; }
    catch { /* Try the next deployment location. */ }
  }
  return defaults;
}
