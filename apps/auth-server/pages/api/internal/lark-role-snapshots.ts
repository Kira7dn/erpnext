import { timingSafeEqual } from "node:crypto";

import type { NextApiRequest, NextApiResponse } from "next";
import { z } from "zod";

import { getDb } from "../../../src/server/db";
import { getEnv } from "../../../src/server/env";
import { disableCaching } from "../../../src/server/http";
import { fetchLarkGroupIds, type LarkSubjectType } from "../../../src/server/lark";
import { audit } from "../../../src/server/audit";

const identityRequestSchema = z.object({
  tenant_key: z.string().min(1),
  subject: z.string().min(1),
  subject_type: z.literal("union_id"),
}).strict();

export const config = { maxDuration: 60 };

function authorized(req: NextApiRequest, secret: string): boolean {
  const supplied = req.headers.authorization?.replace(/^Bearer\s+/i, "") ?? "";
  const left = Buffer.from(supplied);
  const right = Buffer.from(secret);
  return left.length === right.length && timingSafeEqual(left, right);
}

type LarkIdentity = {
  id: bigint;
  tenantKey: string;
  subject: string;
  subjectType: string | null;
  userId: string;
  user: { email: string; displayName: string; status: string };
};

async function refreshIdentity(identity: LarkIdentity) {
  const base = {
    tenant_key: identity.tenantKey,
    subject: identity.subject,
    subject_type: identity.subjectType,
    email: identity.user.email,
    display_name: identity.user.displayName,
  };
  if (identity.user.status !== "ACTIVE") {
    const syncedAt = new Date();
    await getDb().externalIdentity.update({
      where: { id: identity.id },
      data: { groupIds: [], groupsSyncedAt: syncedAt },
    });
    return {
      ...base,
      status: "disabled" as const,
      groups: [],
      groups_synced_at: syncedAt.toISOString(),
    };
  }
  if (identity.subjectType !== "union_id") {
    return { ...base, status: "error" as const, error_code: "identity_reauth_required" };
  }
  try {
    const groupIds = await fetchLarkGroupIds(identity.subject, identity.subjectType as LarkSubjectType);
    const syncedAt = new Date();
    await getDb().externalIdentity.update({
      where: { id: identity.id },
      data: { groupIds, groupsSyncedAt: syncedAt },
    });
    return {
      ...base,
      status: "ok" as const,
      groups: groupIds,
      groups_synced_at: syncedAt.toISOString(),
    };
  } catch {
    await audit({
      eventType: "lark.groups.refresh",
      outcome: "failure",
      userId: identity.userId,
      detail: { error_code: "lark_group_refresh_failed" },
    }).catch(() => undefined);
    return { ...base, status: "error" as const, error_code: "lark_group_refresh_failed" };
  }
}

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  const env = getEnv();
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    res.status(405).end();
    return;
  }
  if (!env.LARK_GROUP_SYNC_ENABLED || !env.LETRON_SSO_SYNC_SECRET) {
    res.status(503).json({ error: "lark_group_sync_disabled" });
    return;
  }
  if (!authorized(req, env.LETRON_SSO_SYNC_SECRET)) {
    res.status(401).json({ error: "unauthorized" });
    return;
  }

  const parsed = identityRequestSchema.safeParse(req.body);
  if (!parsed.success || parsed.data.tenant_key !== env.LARK_ALLOWED_TENANT_KEY) {
    res.status(400).json({ error: "invalid_identity" });
    return;
  }
  const identity = await getDb().externalIdentity.findUnique({
    where: {
      provider_tenantKey_subject: {
        provider: "lark",
        tenantKey: parsed.data.tenant_key,
        subject: parsed.data.subject,
      },
    },
    include: { user: true },
  });
  if (!identity || identity.subjectType !== parsed.data.subject_type) {
    res.status(404).json({ error: "identity_not_found" });
    return;
  }
  res.status(200).json({
    version: 2,
    generated_at: new Date().toISOString(),
    snapshot: await refreshIdentity(identity),
  });
}
