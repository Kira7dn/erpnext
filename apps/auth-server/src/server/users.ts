import { getDb } from "./db";
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

export async function refreshLarkGroupsForUser(userId: string): Promise<void> {
  const identity = await getDb().externalIdentity.findFirst({
    where: { provider: "lark", userId },
    orderBy: { id: "asc" },
  });
  if (!identity || identity.subjectType !== "union_id") {
    throw new Error("LARK_IDENTITY_REAUTH_REQUIRED");
  }
  const groupIds = await fetchLarkGroupIds(identity.subject, identity.subjectType);
  await getDb().externalIdentity.update({
    where: { id: identity.id },
    data: { groupIds, groupsSyncedAt: new Date() },
  });
}
