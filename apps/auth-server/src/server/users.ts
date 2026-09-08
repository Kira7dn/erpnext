import { getDb } from "./db";
import { getEnv } from "./env";
import { fetchLarkGroupIds, type LarkSubjectType } from "./lark";

export type LarkIdentity = {
  tenantKey: string;
  subject: string;
  subjectType: LarkSubjectType;
  email: string;
  displayName: string;
  avatarUrl?: string;
  groupIds?: string[];
};

export async function upsertLarkUser(identity: LarkIdentity) {
  const email = identity.email.trim().toLowerCase();
  return getDb().$transaction(async (tx) => {
    const existingIdentity = await tx.externalIdentity.findUnique({
      where: {
        provider_tenantKey_subject: {
          provider: "lark",
          tenantKey: identity.tenantKey,
          subject: identity.subject,
        },
      },
      include: { user: true },
    });

    if (existingIdentity) {
      const user = await tx.user.update({
        where: { id: existingIdentity.userId },
        data: { email, displayName: identity.displayName, avatarUrl: identity.avatarUrl },
      });
      await tx.externalIdentity.update({
        where: { id: existingIdentity.id },
        data: {
          email,
          subjectType: identity.subjectType,
          lastSeenAt: new Date(),
          ...(identity.groupIds ? { groupIds: identity.groupIds, groupsSyncedAt: new Date() } : {}),
        },
      });
      return user;
    }

    const emailOwner = await tx.user.findUnique({ where: { email }, select: { id: true } });
    if (emailOwner) throw new Error("LARK_EMAIL_IDENTITY_CONFLICT");
    const user = await tx.user.create({
      data: { email, displayName: identity.displayName, avatarUrl: identity.avatarUrl },
    });
    await tx.externalIdentity.create({
      data: {
        provider: "lark",
        tenantKey: identity.tenantKey,
        subject: identity.subject,
        subjectType: identity.subjectType,
        userId: user.id,
        email,
        groupIds: identity.groupIds ?? [],
        groupsSyncedAt: identity.groupIds ? new Date() : undefined,
      },
    });
    return user;
  });
}

export async function syncLarkGroupsIfStale(userId: string): Promise<string[]> {
  const identity = await getDb().externalIdentity.findFirst({
    where: { provider: "lark", userId },
    orderBy: { id: "asc" },
  });
  if (!identity || identity.subjectType !== "union_id") {
    throw new Error("LARK_IDENTITY_REAUTH_REQUIRED");
  }
  const staleAt = Date.now() - getEnv().AUTH_GROUP_SYNC_STALE_SECONDS * 1000;
  if (identity.groupsSyncedAt && identity.groupsSyncedAt.getTime() > staleAt) return identity.groupIds;

  const now = new Date();
  const leaseUntil = new Date(Date.now() + Math.min(getEnv().AUTH_GROUP_SYNC_STALE_SECONDS, 30) * 1000);
  const claimed = await getDb().externalIdentity.updateMany({
    where: { id: identity.id, OR: [{ syncLeaseUntil: null }, { syncLeaseUntil: { lt: now } }] },
    data: { syncLeaseUntil: leaseUntil },
  });
  if (claimed.count !== 1) {
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 100));
      const refreshed = await getDb().externalIdentity.findUnique({ where: { id: identity.id }, select: { groupsSyncedAt: true } });
      if (refreshed?.groupsSyncedAt && refreshed.groupsSyncedAt.getTime() > staleAt) {
        const current = await getDb().externalIdentity.findUnique({ where: { id: identity.id }, select: { groupIds: true } });
        return current?.groupIds ?? [];
      }
    }
    throw new Error("LARK_GROUP_SYNC_BUSY");
  }
  try {
    const groupIds = await fetchLarkGroupIds(identity.subject, identity.subjectType);
    await getDb().externalIdentity.update({ where: { id: identity.id }, data: { groupIds, groupsSyncedAt: new Date(), syncLeaseUntil: null } });
    return groupIds;
  } catch (error) {
    await getDb().externalIdentity.updateMany({ where: { id: identity.id }, data: { syncLeaseUntil: null } }).catch(() => undefined);
    throw error;
  }
}
