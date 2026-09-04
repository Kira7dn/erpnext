import type { NextApiRequest, NextApiResponse } from "next";

import { getDb } from "../../src/server/db";
import { getEnv } from "../../src/server/env";

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    res.status(405).end();
    return;
  }
  try {
    const env = getEnv();
    await getDb().$queryRaw`SELECT 1`;
    const staleBefore = new Date(Date.now() - env.AUTH_GROUP_SYNC_STALE_SECONDS * 1000);
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
        enabled: env.LARK_GROUP_SYNC_ENABLED,
        refresh_mode: "on-demand",
        known_identities: knownIdentities,
        stale_identities: staleIdentities,
      },
    });
  } catch {
    res.status(503).json({ status: "unavailable" });
  }
}
