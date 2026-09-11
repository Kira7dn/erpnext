import { getDb } from "./db";
import { parseAccessPolicy, type AccessPolicy } from "./access-policy";
import { cacheGet, cacheSet, policyCacheKey } from "./cache";
import { AUTH_FEATURE_CONFIG } from "./env";

export async function getPublishedPolicy(): Promise<{ policy: AccessPolicy; version: number; sha256: string } | null> {
  const cached = await cacheGet<{ policy: AccessPolicy; version: number; sha256: string }>(policyCacheKey);
  if (cached) return cached;
  const row = await getDb().accessPolicy.findFirst({ where: { status: "PUBLISHED" }, orderBy: { version: "desc" } });
  if (!row) return null;
  const policy = { policy: parseAccessPolicy(row.policy), version: row.version, sha256: row.sha256 };
  await cacheSet(policyCacheKey, policy, AUTH_FEATURE_CONFIG.policyCacheTtlSeconds);
  return policy;
}
