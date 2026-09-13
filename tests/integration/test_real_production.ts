import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "../..");

async function main(): Promise<void> {
  const envFile = resolve(root, ".env.production");
  const content = await readFile(envFile, "utf8");
  for (const line of content.split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
    if (!match) continue;
    const [, key, rawValue] = match;
    if (process.env[key] !== undefined) continue;
    process.env[key] = rawValue.replace(/^['"]|['"]$/g, "");
  }

  process.env.REALTEST_ENV_FILE = ".env.production";
  process.env.ERP_BASE_URL = "https://erp.letron.vn";
  process.env.PORTAL_BASE_URL = "https://auth.letron.vn";
  process.env.LETRON_ERP_APP_BASE_URL = "https://erp.letron.vn";
  process.env.LETRON_AUTH_BASE_URL = "https://auth.letron.vn";
  process.env.REALTEST_APPROVAL_HEADER = "production";

  await import("./test_real_mr.ts");
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
