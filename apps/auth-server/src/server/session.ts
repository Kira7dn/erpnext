import type { NextApiRequest, NextApiResponse } from "next";

import { getDb } from "./db";
import { getEnv } from "./env";
import { appendSetCookie, parseCookies, serializeCookie } from "./http";
import { randomToken, sha256 } from "./crypto";
import { fetchLarkGroupIds } from "./lark";

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

function secureCookie(): boolean {
  return getEnv().AUTH_BASE_URL.startsWith("https://");
}

export async function createSession(userId: string): Promise<{ token: string; expiresAt: Date }> {
  const token = randomToken();
  const expiresAt = new Date(Date.now() + getEnv().AUTH_SESSION_TTL_SECONDS * 1000);
  await getDb().ssoSession.create({ data: { tokenHash: sha256(token), userId, expiresAt } });
  return { token, expiresAt };
}

export function setSessionCookie(res: NextApiResponse, token: string, expiresAt: Date): void {
  appendSetCookie(res, serializeCookie(SESSION_COOKIE, token, {
    expires: expiresAt,
    secure: secureCookie(),
    domain: getEnv().AUTH_COOKIE_DOMAIN,
  }));
}

export function clearSessionCookie(res: NextApiResponse): void {
  appendSetCookie(res, serializeCookie(SESSION_COOKIE, "", {
    maxAge: 0,
    expires: new Date(0),
    secure: secureCookie(),
    domain: getEnv().AUTH_COOKIE_DOMAIN,
  }));
}

export function tokenFromRequest(req: NextApiRequest): string | undefined {
  return parseCookies(req.headers.cookie)[SESSION_COOKIE];
}

export async function getUserBySessionToken(token: string | undefined): Promise<AuthenticatedUser | null> {
  if (!token) return null;
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
  let groupIds = identity?.groupIds ?? [];
  const env = getEnv();
  if (env.LARK_GROUP_SYNC_ENABLED && identity) {
    if (identity.subjectType !== "union_id") return null;
    const staleAt = Date.now() - env.AUTH_GROUP_SYNC_STALE_SECONDS * 1000;
    if (!identity.groupsSyncedAt || identity.groupsSyncedAt.getTime() <= staleAt) {
      const now = new Date();
      const leaseUntil = new Date(Date.now() + Math.min(env.AUTH_GROUP_SYNC_STALE_SECONDS, 30) * 1000);
      const claimed = await getDb().externalIdentity.updateMany({
        where: { id: identity.id, OR: [{ syncLeaseUntil: null }, { syncLeaseUntil: { lt: now } }] },
        data: { syncLeaseUntil: leaseUntil },
      });
      if (claimed.count !== 1) {
        // Another instance owns the lease. Wait briefly for its committed
        // snapshot so concurrent Gateway requests do not duplicate Lark calls
        // or turn a normal refresh into a transient logout.
        let refreshedSnapshot = false;
        for (let attempt = 0; attempt < 20; attempt += 1) {
          await new Promise((resolve) => setTimeout(resolve, 100));
          const refreshed = await getDb().externalIdentity.findUnique({ where: { id: identity.id }, select: { groupIds: true, groupsSyncedAt: true } });
          if (refreshed?.groupsSyncedAt && refreshed.groupsSyncedAt.getTime() > staleAt) {
            groupIds = refreshed.groupIds;
            refreshedSnapshot = true;
            break;
          }
        }
        if (!refreshedSnapshot) return null;
      }
      try {
        groupIds = await fetchLarkGroupIds(identity.subject, "union_id");
        await getDb().externalIdentity.update({ where: { id: identity.id }, data: { groupIds, groupsSyncedAt: new Date(), syncLeaseUntil: null } });
      } catch {
        await getDb().externalIdentity.updateMany({ where: { id: identity.id }, data: { syncLeaseUntil: null } }).catch(() => undefined);
        // Do not authorize Portal pages or APIs with an unverified stale snapshot.
        return null;
      }
    }
  }
  return {
    id: session.user.id,
    email: session.user.email,
    displayName: session.user.displayName,
    avatarUrl: session.user.avatarUrl,
    groupIds,
    tenantKey: identity?.tenantKey ?? null,
    subject: identity?.subject ?? null,
    subjectType: identity?.subjectType ?? null,
  };
}

export async function rotateSession(req: NextApiRequest, res: NextApiResponse, userId: string): Promise<void> {
  const oldToken = tokenFromRequest(req);
  const next = await getDb().$transaction(async (tx) => {
    if (oldToken) {
      await tx.ssoSession.updateMany({
        where: { tokenHash: sha256(oldToken), revokedAt: null },
        data: { revokedAt: new Date() },
      });
    }
    const token = randomToken();
    const expiresAt = new Date(Date.now() + getEnv().AUTH_SESSION_TTL_SECONDS * 1000);
    await tx.ssoSession.create({ data: { tokenHash: sha256(token), userId, expiresAt } });
    return { token, expiresAt };
  });
  setSessionCookie(res, next.token, next.expiresAt);
}

export async function revokeRequestSession(req: NextApiRequest): Promise<void> {
  const token = tokenFromRequest(req);
  if (!token) return;
  await getDb().ssoSession.updateMany({
    where: { tokenHash: sha256(token), revokedAt: null },
    data: { revokedAt: new Date() },
  });
}
