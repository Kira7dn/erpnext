import { Redis } from "@upstash/redis";

import { getEnv } from "./env";

let redis: Redis | null | undefined;

function getRedis(): Redis | null {
  if (redis !== undefined) return redis;
  const env = getEnv();
  redis = new Redis({ url: env.KV_REST_API_URL, token: env.KV_REST_API_TOKEN });
  return redis;
}

export async function cacheGet<T>(key: string): Promise<T | null> {
  const client = getRedis();
  if (!client) return null;
  try {
    return await client.get<T>(key);
  } catch {
    return null;
  }
}

export async function cacheSet<T>(key: string, value: T, ttlSeconds: number): Promise<void> {
  const client = getRedis();
  if (!client) return;
  try {
    await client.set(key, value, { ex: Math.max(1, Math.floor(ttlSeconds)) });
  } catch {
    // Cache failure must never turn an authenticated request into an outage.
  }
}

export async function cacheDelete(key: string): Promise<void> {
  const client = getRedis();
  if (!client) return;
  try {
    await client.del(key);
  } catch {
    // Cache failure is intentionally fail-open; the authoritative DB remains available.
  }
}

export async function invalidatePolicyCache(): Promise<void> {
  await cacheDelete(policyCacheKey);
}

export function sessionCacheKey(tokenHash: string): string { return `letron:sso:session:${tokenHash}`; }
export const policyCacheKey = "letron:sso:policy:published";
