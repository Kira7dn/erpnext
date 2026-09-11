import "server-only";

import { createHash, randomBytes } from "node:crypto";
import { Redis } from "@upstash/redis";
import { cookies } from "next/headers";

const SESSION_TTL_SECONDS = 8 * 60 * 60;
export const ERP_SESSION_COOKIE = "__Host-letron_erp";

export type ErpAuthUser = {
  id: string;
  email: string;
  displayName: string;
  avatarUrl: string | null;
};

type ErpSession = { user: ErpAuthUser; gatewaySession: string; expiresAt: string };
let redis: Redis | undefined;

function store(): Redis {
  if (redis) return redis;
  const url = process.env.KV_REST_API_URL;
  const token = process.env.KV_REST_API_TOKEN;
  if (!url || !token) throw new Error("ERP session storage is not configured");
  redis = new Redis({ url, token });
  return redis;
}

function hash(value: string): string { return createHash("sha256").update(value).digest("hex"); }
function key(token: string): string { return `erp:sso:session:${hash(token)}`; }
function newToken(): string { return randomBytes(32).toString("base64url"); }

export async function createErpSession(user: ErpAuthUser, gatewaySession: string): Promise<{ token: string; expiresAt: Date }> {
  const token = newToken();
  const expiresAt = new Date(Date.now() + SESSION_TTL_SECONDS * 1000);
  await store().set(key(token), { user, gatewaySession, expiresAt: expiresAt.toISOString() } satisfies ErpSession, { ex: SESSION_TTL_SECONDS });
  return { token, expiresAt };
}

export async function getErpSession(rawToken?: string | null): Promise<(ErpSession & { token: string }) | null> {
  const token = rawToken ?? (await cookies()).get(ERP_SESSION_COOKIE)?.value;
  if (!token) return null;
  const session = await store().get<ErpSession>(key(token));
  if (!session || Date.parse(session.expiresAt) <= Date.now()) return null;
  return { ...session, token };
}

export async function revokeErpSession(token?: string | null): Promise<void> {
  if (token) await store().del(key(token));
}
