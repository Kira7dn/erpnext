import type { NextApiRequest, NextApiResponse } from "next";

import { getDb } from "../../src/server/db";
import { AUTH_FEATURE_CONFIG, getEnv } from "../../src/server/env";

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    res.status(405).end();
    return;
  }
  try {
    const env = getEnv();
    await getDb().$queryRaw`SELECT 1`;
    const staleBefore = new Date(Date.now() - AUTH_FEATURE_CONFIG.groupSyncStaleSeconds * 1000);
    const [knownIdentities, staleIdentities] = await Promise.all([
      getDb().externalIdentity.count({ where: { provider: "lark" } }),
      getDb().externalIdentity.count({
        where: {
          provider: "lark",
          OR: [{ groupsSyncedAt: null }, { groupsSyncedAt: { lt: staleBefore } }],
        },
      }),
    ]);
    res.status(200).json({
      status: "ok",
      lark_group_sync: {
        enabled: AUTH_FEATURE_CONFIG.larkGroupSyncEnabled,
        refresh_mode: "on-demand",
        known_identities: knownIdentities,
        stale_identities: staleIdentities,
      },
    });
  } catch {
    res.status(503).json({ status: "unavailable" });
  }
}
