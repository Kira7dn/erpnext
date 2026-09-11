import { getDb } from "./db";
import { randomToken, sha256 } from "./crypto";
import { getEnv } from "./env";

const HANDOFF_TTL_MS = 2 * 60 * 1000;

export async function createErpHandoff(
  userId: string,
): Promise<{ code: string; expiresAt: Date }> {
  const code = randomToken(32);
  const expiresAt = new Date(Date.now() + HANDOFF_TTL_MS);
  await getDb().erpHandoff.create({
    data: { codeHash: sha256(code), userId, expiresAt },
  });
  return { code, expiresAt };
}

export async function consumeErpHandoff(code: string): Promise<{
  gatewayToken: string;
  gatewayExpiresAt: Date;
  user: {
    id: string;
    email: string;
    displayName: string;
    avatarUrl: string | null;
  };
} | null> {
  const gatewayToken = randomToken(32);
  const gatewayExpiresAt = new Date(
    Date.now() + getEnv().LETRON_ERP_SESSION_TTL_SECONDS * 1000,
  );
  return getDb().$transaction(async (tx) => {
    const row = await tx.erpHandoff.findFirst({
      where: {
        codeHash: sha256(code),
        consumedAt: null,
        expiresAt: { gt: new Date() },
      },
      include: { user: true },
    });
    if (!row || row.user.status !== "ACTIVE") return null;
    const consumed = await tx.erpHandoff.updateMany({
      where: { id: row.id, consumedAt: null, expiresAt: { gt: new Date() } },
      data: { consumedAt: new Date() },
    });
    if (consumed.count !== 1) return null;
    await tx.erpGatewaySession.create({
      data: {
        tokenHash: sha256(gatewayToken),
        userId: row.userId,
        expiresAt: gatewayExpiresAt,
      },
    });
    return {
      gatewayToken,
      gatewayExpiresAt,
      user: {
        id: row.user.id,
        email: row.user.email,
        displayName: row.user.displayName,
        avatarUrl: row.user.avatarUrl,
      },
    };
  });
}

export async function revokeErpGatewaySessions(userId: string): Promise<void> {
  await getDb().erpGatewaySession.updateMany({
    where: { userId, revokedAt: null },
    data: { revokedAt: new Date() },
  });
}

export async function revokeErpGatewaySession(token: string): Promise<void> {
  const tokenHash = sha256(token);
  const session = await getDb().erpGatewaySession.findUnique({
    where: { tokenHash },
    select: { userId: true },
  });
  if (!session) return;
  const now = new Date();
  await getDb().$transaction([
    getDb().erpGatewaySession.updateMany({
      where: { tokenHash, revokedAt: null },
      data: { revokedAt: now },
    }),
    getDb().ssoSession.updateMany({
      where: { userId: session.userId, revokedAt: null },
      data: { revokedAt: now },
    }),
  ]);
}
