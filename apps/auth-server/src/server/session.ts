import type { NextApiRequest, NextApiResponse } from "next";

import { getDb } from "./db";
import { AUTH_FEATURE_CONFIG, getEnv } from "./env";
import { appendSetCookie, parseCookies, requestIsSecure, serializeCookie } from "./http";
import { randomToken, sha256 } from "./crypto";
import { cacheDelete, cacheGet, cacheSet, sessionCacheKey } from "./cache";

export const SESSION_COOKIE = "letron_sso";

export type AuthenticatedUser = {
  id: string;
  email: string;
  displayName: string;
  avatarUrl: string | null;
  groupIds: string[];
  tenantKey: string | null;
  subject: string | null;
  subjectType: string | null;
};

function cookieOptions(req: NextApiRequest): { secure: boolean } {
  // Auth sessions are intentionally host-only. ERP receives its own BFF
  // session after the one-time handoff exchange; no parent-domain cookie is
  // shared across applications.
  return { secure: requestIsSecure(req) };
}

export async function createSession(userId: string): Promise<{ token: string; expiresAt: Date }> {
  const token = randomToken();
  const expiresAt = new Date(Date.now() + AUTH_FEATURE_CONFIG.sessionTtlSeconds * 1000);
  await getDb().ssoSession.create({ data: { tokenHash: sha256(token), userId, expiresAt } });
  return { token, expiresAt };
}

export function setSessionCookie(req: NextApiRequest, res: NextApiResponse, token: string, expiresAt: Date): void {
  appendSetCookie(res, serializeCookie(SESSION_COOKIE, token, {
    expires: expiresAt,
    ...cookieOptions(req),
  }));
}

export function clearSessionCookie(req: NextApiRequest, res: NextApiResponse): void {
  appendSetCookie(res, serializeCookie(SESSION_COOKIE, "", {
    maxAge: 0,
    expires: new Date(0),
    ...cookieOptions(req),
  }));
}

export function tokenFromRequest(req: NextApiRequest): string | undefined {
  return parseCookies(req.headers.cookie)[SESSION_COOKIE];
}

export async function getUserBySessionToken(token: string | undefined): Promise<AuthenticatedUser | null> {
  if (!token) return null;
  const tokenHash = sha256(token);
  const cached = await cacheGet<{ user: AuthenticatedUser; expiresAt: string }>(sessionCacheKey(tokenHash));
  if (cached && new Date(cached.expiresAt).getTime() > Date.now()) return cached.user;
  const session = await getDb().ssoSession.findFirst({
    where: {
      tokenHash: sha256(token),
      revokedAt: null,
      expiresAt: { gt: new Date() },
      user: { status: "ACTIVE" },
    },
    include: {
      user: {
        include: {
          identities: {
            where: { provider: "lark" },
            orderBy: { id: "asc" },
            take: 1,
          },
        },
      },
    },
  });
  if (!session) return null;
  const identity = session.user.identities[0];
  const groupIds = identity?.groupIds ?? [];
  const user = {
    id: session.user.id,
    email: session.user.email,
    displayName: session.user.displayName,
    avatarUrl: session.user.avatarUrl,
    groupIds,
    tenantKey: identity?.tenantKey ?? null,
    subject: identity?.subject ?? null,
    subjectType: identity?.subjectType ?? null,
  };
  await cacheSet(sessionCacheKey(tokenHash), { user, expiresAt: session.expiresAt.toISOString() }, Math.min(AUTH_FEATURE_CONFIG.sessionCacheTtlSeconds, Math.max(1, Math.ceil((session.expiresAt.getTime() - Date.now()) / 1000))));
  return user;
}

export async function getUserByGatewaySessionToken(token: string | undefined): Promise<AuthenticatedUser | null> {
  if (!token) return null;
  const session = await getDb().erpGatewaySession.findFirst({
    where: { tokenHash: sha256(token), revokedAt: null, expiresAt: { gt: new Date() }, user: { status: "ACTIVE" } },
    include: { user: { include: { identities: { where: { provider: "lark" }, orderBy: { id: "asc" }, take: 1 } } } },
  });
  if (!session) return null;
  const identity = session.user.identities[0];
  return {
    id: session.user.id,
    email: session.user.email,
    displayName: session.user.displayName,
    avatarUrl: session.user.avatarUrl,
    groupIds: identity?.groupIds ?? [],
    tenantKey: identity?.tenantKey ?? null,
    subject: identity?.subject ?? null,
    subjectType: identity?.subjectType ?? null,
  };
}

export async function rotateSession(req: NextApiRequest, res: NextApiResponse, userId: string): Promise<void> {
  const oldToken = tokenFromRequest(req);
  if (oldToken) await cacheDelete(sessionCacheKey(sha256(oldToken)));
  const next = await getDb().$transaction(async (tx) => {
    if (oldToken) {
      await tx.ssoSession.updateMany({
        where: { tokenHash: sha256(oldToken), revokedAt: null },
        data: { revokedAt: new Date() },
      });
    }
    const token = randomToken();
    const expiresAt = new Date(Date.now() + AUTH_FEATURE_CONFIG.sessionTtlSeconds * 1000);
    await tx.ssoSession.create({ data: { tokenHash: sha256(token), userId, expiresAt } });
    return { token, expiresAt };
  });
  setSessionCookie(req, res, next.token, next.expiresAt);
}

export async function revokeRequestSession(req: NextApiRequest): Promise<void> {
  const token = tokenFromRequest(req);
  if (!token) return;
  await cacheDelete(sessionCacheKey(sha256(token)));
  await getDb().ssoSession.updateMany({
    where: { tokenHash: sha256(token), revokedAt: null },
    data: { revokedAt: new Date() },
  });
}
