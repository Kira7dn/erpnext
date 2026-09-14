import { config as loadDotEnv } from "dotenv";
import { resolve } from "node:path";
import { z } from "zod";

let cachedEnv: AuthEnv | undefined;
let loadedFiles = false;

export const AUTH_FEATURE_CONFIG = {
  larkGroupSyncEnabled: true,
  groupSyncStaleSeconds: 60,
  sessionTtlSeconds: 28800,
  sessionCacheTtlSeconds: 30,
  policyCacheTtlSeconds: 30,
} as const;

const schema = z.object({
  LETRON_AUTH_BASE_URL: z.url().transform((value) => value.replace(/\/$/, "")),
  DATABASE_URL: z.string().min(1),
  LARK_APP_ID: z.string().min(1),
  LARK_APP_SECRET: z.string().min(1),
  LARK_ALLOWED_TENANT_KEY: z.string().min(1),
  FRAPPE_ERP_NEXT_URL: z.url().transform((value) => value.replace(/\/$/, "")),
  LETRON_ERP_APP_BASE_URL: z
    .url()
    .transform((value) => value.replace(/\/$/, "")),
  LETRON_ERP_SESSION_TTL_SECONDS: z.coerce
    .number()
    .int()
    .positive()
    .default(86400),
  LETRON_INTERNAL_API_SECRET: z.string().min(32).optional(),
  LETRON_AUTH_GATEWAY_SECRET: z.string().min(32),
  LETRON_AUTH_TO_ERP_JIT_SECRET: z.string().min(32),
  AUTH_DATA_ENCRYPTION_KEY: z.string().min(1),
  OIDC_COOKIE_KEYS: z.string().min(1),
  OIDC_JWKS: z.string().min(1),
  KV_REST_API_URL: z.url().transform((value) => value.replace(/\/$/, "")),
  KV_REST_API_TOKEN: z.string().min(1),
  AWS_ACCESS_KEY_ID: z.string().min(1).optional(),
  AWS_SECRET_ACCESS_KEY: z.string().min(1).optional(),
  AWS_DEFAULT_REGION: z.string().default("ap-southeast-1"),
  S3_BUCKET_NAME: z.string().default("letron-erp-backups"),
  NODE_ENV: z
    .enum(["development", "test", "production"])
    .default("development"),
});

export type AuthEnv = z.infer<typeof schema>;

function loadLocalFiles(): void {
  if (loadedFiles || process.env.VERCEL) return;
  loadedFiles = true;
  loadDotEnv({
    path: resolve(process.cwd(), "../../.env"),
    override: false,
    quiet: true,
  });
}

export function getEnv(): AuthEnv {
  if (cachedEnv) return cachedEnv;
  loadLocalFiles();
  cachedEnv = schema.parse(process.env);
  if (
    AUTH_FEATURE_CONFIG.larkGroupSyncEnabled &&
    !cachedEnv.LETRON_INTERNAL_API_SECRET
  ) {
    throw new Error(
      "LETRON_INTERNAL_API_SECRET is required when LARK_GROUP_SYNC_ENABLED is true",
    );
  }
  return cachedEnv;
}

export function resetEnvForTests(): void {
  cachedEnv = undefined;
}

export function parseJsonEnv<T>(
  name: "OIDC_COOKIE_KEYS" | "OIDC_JWKS",
  value: string,
): T {
  try {
    return JSON.parse(value) as T;
  } catch {
    throw new Error(`${name} must contain valid JSON`);
  }
}
