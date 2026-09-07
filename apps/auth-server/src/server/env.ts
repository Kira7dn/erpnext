import { config as loadDotEnv } from "dotenv";
import { resolve } from "node:path";
import { z } from "zod";

let cachedEnv: AuthEnv | undefined;
let loadedFiles = false;

const schema = z.object({
  AUTH_BASE_URL: z.url().transform((value) => value.replace(/\/$/, "")),
  AUTH_COOKIE_DOMAIN: z.string().min(1).optional(),
  DATABASE_URL: z.string().min(1),
  LARK_APP_ID: z.string().min(1),
  LARK_APP_SECRET: z.string().min(1),
  LARK_ALLOWED_TENANT_KEY: z.string().min(1),
  LARK_DOMAIN: z.url().default("https://open.larksuite.com").transform((value) => value.replace(/\/$/, "")),
  LARK_GROUP_SYNC_ENABLED: z.stringbool().default(false),
  AUTH_GROUP_SYNC_STALE_SECONDS: z.coerce.number().int().min(60).max(86400).default(600),
  LETRON_SSO_ERP_BASE_URL: z.url().optional().transform((value) => value?.replace(/\/$/, "")),
  LETRON_NEXT_BASE_URL: z.url().optional().transform((value) => value?.replace(/\/$/, "")),
  GLOBAL_ACCESS_ADMIN_GROUP_ID: z.string().min(1).optional(),
  LETRON_SSO_SYNC_SECRET: z.string().min(32).optional(),
  AUTH_ERP_SYNC_SECRET: z.string().min(32).optional(),
  AUTH_DATA_ENCRYPTION_KEY: z.string().min(1),
  OIDC_COOKIE_KEYS: z.string().min(1),
  OIDC_JWKS: z.string().min(1),
  AUTH_SESSION_TTL_SECONDS: z.coerce.number().int().positive().max(86400).default(28800),
  AWS_ACCESS_KEY_ID: z.string().min(1).optional(),
  AWS_SECRET_ACCESS_KEY: z.string().min(1).optional(),
  AWS_DEFAULT_REGION: z.string().default("ap-southeast-1"),
  S3_BUCKET_NAME: z.string().default("letron-erp-backups"),
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
});

export type AuthEnv = z.infer<typeof schema>;

function loadLocalFiles(): void {
  if (loadedFiles || process.env.VERCEL) return;
  loadedFiles = true;
  loadDotEnv({ path: resolve(process.cwd(), ".env.local"), override: false, quiet: true });
  loadDotEnv({ path: resolve(process.cwd(), ".env"), override: false, quiet: true });
  loadDotEnv({ path: resolve(process.cwd(), "../../.env"), override: false, quiet: true });
}

export function getEnv(): AuthEnv {
  if (cachedEnv) return cachedEnv;
  loadLocalFiles();
  cachedEnv = schema.parse(process.env);
  if (cachedEnv.LARK_GROUP_SYNC_ENABLED && !cachedEnv.AUTH_ERP_SYNC_SECRET) {
    throw new Error("AUTH_ERP_SYNC_SECRET is required when LARK_GROUP_SYNC_ENABLED is true");
  }
  return cachedEnv;
}

export function resetEnvForTests(): void {
  cachedEnv = undefined;
}

export function parseJsonEnv<T>(name: "OIDC_COOKIE_KEYS" | "OIDC_JWKS", value: string): T {
  try {
    return JSON.parse(value) as T;
  } catch {
    throw new Error(`${name} must contain valid JSON`);
  }
}
