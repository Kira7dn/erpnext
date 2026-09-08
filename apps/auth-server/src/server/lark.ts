import { z } from "zod";

import { getEnv } from "./env";

const tokenSchema = z.object({
  access_token: z.string().min(1),
});

const tenantTokenSchema = z.object({
  tenant_access_token: z.string().min(1),
  expire: z.number().int().positive().optional(),
});

const groupPageSchema = z.object({
  group_list: z.array(z.string().min(1)).default([]),
  page_token: z.string().min(1).optional(),
  has_more: z.boolean().default(false),
});

const groupCatalogPageSchema = z.object({
  grouplist: z.array(z.object({
    id: z.string().min(1),
    name: z.string().min(1).optional(),
    description: z.string().optional(),
  }).passthrough()).default([]),
  page_token: z.preprocess((value) => value === "" ? undefined : value, z.string().min(1).optional()),
  has_more: z.boolean().default(false),
});

const optionalId = z.preprocess((value) => value === "" ? undefined : value, z.string().min(1).optional());
const optionalEmail = z.preprocess((value) => value === "" ? undefined : value, z.string().email().optional());
const optionalUrl = z.preprocess((value) => value === "" ? undefined : value, z.string().url().optional());
export const LARK_LOGIN_SCOPES = "contact:user.email:readonly";

export function larkCallbackUri(origin = getEnv().AUTH_BASE_URL): string {
  return `${origin.replace(/\/$/, "")}/api/auth/lark/callback`;
}

const userSchema = z.object({
  tenant_key: z.string().min(1),
  union_id: optionalId,
  open_id: optionalId,
  enterprise_email: optionalEmail,
  email: optionalEmail,
  name: z.string().min(1),
  avatar_url: optionalUrl,
});

export type LarkSubjectType = "union_id";

type TenantTokenCache = {
  token: string;
  expiresAt: number;
};

type LarkGlobal = typeof globalThis & { __letronLarkTenantToken?: TenantTokenCache };

function unwrap(data: unknown): unknown {
  if (data && typeof data === "object" && "data" in data) return (data as { data: unknown }).data;
  return data;
}

async function readJson(response: Response): Promise<unknown> {
  const payload: unknown = await response.json();
  if (!response.ok) throw new Error(`Lark request failed with HTTP ${response.status}`);
  if (payload && typeof payload === "object" && "code" in payload) {
    const code = (payload as { code?: unknown }).code;
    if (typeof code === "number" && code !== 0) throw new Error(`Lark rejected request with code ${code}`);
  }
  return payload;
}

export function buildLarkAuthorizationUrl(input: {
  state: string;
  codeChallenge: string;
  redirectUri?: string;
}): URL {
  const env = getEnv();
  const url = new URL("/open-apis/authen/v1/authorize", env.LARK_DOMAIN);
  url.searchParams.set("client_id", env.LARK_APP_ID);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("redirect_uri", input.redirectUri ?? larkCallbackUri());
  url.searchParams.set("state", input.state);
  url.searchParams.set("scope", LARK_LOGIN_SCOPES);
  url.searchParams.set("code_challenge", input.codeChallenge);
  url.searchParams.set("code_challenge_method", "S256");
  return url;
}

export async function exchangeLarkCode(code: string, codeVerifier: string, redirectUri = larkCallbackUri()): Promise<string> {
  const env = getEnv();
  const response = await fetch(new URL("/open-apis/authen/v2/oauth/token", env.LARK_DOMAIN), {
    method: "POST",
    headers: { "content-type": "application/json; charset=utf-8" },
    body: JSON.stringify({
      grant_type: "authorization_code",
      client_id: env.LARK_APP_ID,
      client_secret: env.LARK_APP_SECRET,
      code,
      redirect_uri: redirectUri,
      code_verifier: codeVerifier,
    }),
    signal: AbortSignal.timeout(10_000),
  });
  return tokenSchema.parse(unwrap(await readJson(response))).access_token;
}

export async function fetchLarkIdentity(accessToken: string) {
  const env = getEnv();
  const response = await fetch(new URL("/open-apis/authen/v1/user_info", env.LARK_DOMAIN), {
    headers: { authorization: `Bearer ${accessToken}` },
    signal: AbortSignal.timeout(10_000),
  });
  const user = userSchema.parse(unwrap(await readJson(response)));
  if (user.tenant_key !== env.LARK_ALLOWED_TENANT_KEY) throw new Error("LARK_TENANT_NOT_ALLOWED");
  const subject = user.union_id;
  if (!subject) throw new Error("LARK_UNION_ID_MISSING");
  const email = user.enterprise_email || user.email;
  if (!email) throw new Error("LARK_EMAIL_MISSING");
  return {
    tenantKey: user.tenant_key,
    subject,
    subjectType: "union_id" as const,
    email,
    displayName: user.name,
    avatarUrl: user.avatar_url,
  };
}

async function getTenantAccessToken(): Promise<string> {
  const globalScope = globalThis as LarkGlobal;
  const now = Date.now();
  if (globalScope.__letronLarkTenantToken && globalScope.__letronLarkTenantToken.expiresAt > now + 30_000) {
    return globalScope.__letronLarkTenantToken.token;
  }

  const env = getEnv();
  const response = await fetch(new URL("/open-apis/auth/v3/tenant_access_token/internal", env.LARK_DOMAIN), {
    method: "POST",
    headers: { "content-type": "application/json; charset=utf-8" },
    body: JSON.stringify({ app_id: env.LARK_APP_ID, app_secret: env.LARK_APP_SECRET }),
    signal: AbortSignal.timeout(10_000),
  });
  const payload = tenantTokenSchema.parse(await readJson(response));
  globalScope.__letronLarkTenantToken = {
    token: payload.tenant_access_token,
    expiresAt: now + Math.max(60, payload.expire ?? 3600) * 1000,
  };
  return payload.tenant_access_token;
}

export async function fetchLarkGroupIds(subject: string, subjectType: LarkSubjectType): Promise<string[]> {
  const env = getEnv();
  const tenantAccessToken = await getTenantAccessToken();
  const groupIds = new Set<string>();
  let pageToken: string | undefined;

  for (let page = 0; page < 100; page += 1) {
    const url = new URL("/open-apis/contact/v3/group/member_belong", env.LARK_DOMAIN);
    url.searchParams.set("member_id", subject);
    url.searchParams.set("member_id_type", subjectType);
    url.searchParams.set("page_size", "500");
    if (pageToken) url.searchParams.set("page_token", pageToken);
    const response = await fetch(url, {
      headers: { authorization: `Bearer ${tenantAccessToken}` },
      signal: AbortSignal.timeout(10_000),
    });
    const data = groupPageSchema.parse(unwrap(await readJson(response)));
    data.group_list.forEach((groupId) => groupIds.add(groupId));
    if (!data.has_more) return [...groupIds].sort();
    if (!data.page_token || data.page_token === pageToken) throw new Error("LARK_GROUP_PAGINATION_INVALID");
    pageToken = data.page_token;
  }

  throw new Error("LARK_GROUP_PAGINATION_LIMIT");
}

export async function fetchLarkGroupCatalog(): Promise<Array<{ id: string; name: string; description?: string }>> {
  const env = getEnv();
  const tenantAccessToken = await getTenantAccessToken();
  const groups = new Map<string, { id: string; name: string; description?: string }>();
  let pageToken: string | undefined;
  for (let page = 0; page < 100; page += 1) {
    const url = new URL("/open-apis/contact/v3/group/simplelist", env.LARK_DOMAIN);
    url.searchParams.set("page_size", "100");
    if (pageToken) url.searchParams.set("page_token", pageToken);
    const response = await fetch(url, { headers: { authorization: `Bearer ${tenantAccessToken}` }, signal: AbortSignal.timeout(10_000) });
    const data = groupCatalogPageSchema.parse(unwrap(await readJson(response)));
    data.grouplist.forEach((group) => groups.set(group.id, { id: group.id, name: group.name ?? group.id, description: group.description }));
    if (!data.has_more) return [...groups.values()].sort((a, b) => a.name.localeCompare(b.name));
    if (!data.page_token || data.page_token === pageToken) throw new Error("LARK_GROUP_CATALOG_PAGINATION_INVALID");
    pageToken = data.page_token;
  }
  throw new Error("LARK_GROUP_CATALOG_PAGINATION_LIMIT");
}

export function resetLarkTokenCacheForTests(): void {
  delete (globalThis as LarkGlobal).__letronLarkTenantToken;
}
