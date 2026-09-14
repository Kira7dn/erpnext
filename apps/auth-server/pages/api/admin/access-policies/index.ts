import type { NextApiRequest, NextApiResponse } from "next";
import { Prisma } from "../../../../generated/prisma/client";

import { adminUser, isJsonRequest } from "../../../../src/server/admin";
import { audit } from "../../../../src/server/audit";
import { getDb } from "../../../../src/server/db";
import { disableCaching } from "../../../../src/server/http";
import { invalidatePolicyCache } from "../../../../src/server/cache";
import { parseAccessPolicy, validatePolicy } from "../../../../src/server/access-policy";
import { fetchLarkGroupCatalog } from "../../../../src/server/lark";

async function validateLiveLarkGroups(policy: ReturnType<typeof validatePolicy>["policy"]): Promise<void> {
  const catalog = await fetchLarkGroupCatalog();
  const known = new Set(catalog.map((group) => group.id));
  const referenced = policy.entitlements.flatMap((entitlement) => entitlement.larkGroupIds);
  if (!known.has(policy.requiredAccessGroupId)) throw new Error("requiredAccessGroupId is not a current Lark User Group");
  const unknown = [...new Set(referenced.filter((groupId) => !known.has(groupId)))];
  if (unknown.length) throw new Error(`Policy references unknown Lark User Group: ${unknown.join(", ")}`);
}

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (!isJsonRequest(req)) { res.status(406).json({ error: "json_required" }); return; }
  const actor = await adminUser(req);
  if (!actor) { res.status(403).json({ error: "global_access_admin_required" }); return; }

  if (req.method === "GET") {
    const policies = await getDb().accessPolicy.findMany({ orderBy: { version: "desc" }, take: 50 });
    res.status(200).json({ policies: policies.map((policy) => ({ ...policy, policy: parseAccessPolicy(policy.policy) })) });
    return;
  }
  if (req.method !== "POST") { res.setHeader("Allow", "GET, POST"); res.status(405).end(); return; }

  try {
    const checked = validatePolicy(req.body);
    await validateLiveLarkGroups(checked.policy);
    const policy = await getDb().$transaction(async (tx) => {
      // Autosave can be triggered by several browser tabs at once. Serialize
      // version allocation, ERP publication, and status transitions in the DB
      // so concurrent saves cannot deadlock or publish the same version.
      await tx.$executeRawUnsafe("SELECT pg_advisory_xact_lock(74192601)");
      const latest = await tx.accessPolicy.findFirst({ orderBy: { version: "desc" }, select: { version: true } });
      const draft = await tx.accessPolicy.create({
        data: {
          version: (latest?.version ?? 0) + 1,
          status: "PUBLISHED",
          policy: checked.policy as Prisma.InputJsonValue,
          sha256: checked.sha256,
          createdBy: actor.id,
        },
      });
      await tx.accessPolicy.updateMany({ where: { status: "PUBLISHED" }, data: { status: "SUPERSEDED", supersededAt: new Date() } });
      return tx.accessPolicy.update({ where: { id: draft.id }, data: { status: "PUBLISHED", publishedAt: new Date() } });
    }, { maxWait: 10000, timeout: 30000 });
    await invalidatePolicyCache();
    await audit({ eventType: "access_policy.published", outcome: "success", userId: actor.id, detail: { policy_id: policy.id, version: policy.version } });
    res.status(201).json({ policy });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "invalid_policy";
    const status = detail.startsWith("ERP policy publication failed") ? 502 : detail.includes("Deadlock") ? 503 : 400;
    res.status(status).json({ error: status === 400 ? "invalid_access_policy" : "access_policy_publish_failed", detail });
  }
}
