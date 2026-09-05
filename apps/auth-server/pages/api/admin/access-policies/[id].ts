import type { NextApiRequest, NextApiResponse } from "next";

import { adminUser, isJsonRequest } from "../../../../src/server/admin";
import { disableCaching } from "../../../../src/server/http";

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (!isJsonRequest(req)) { res.status(406).json({ error: "json_required" }); return; }
  const actor = await adminUser(req);
  if (!actor) { res.status(403).json({ error: "global_access_admin_required" }); return; }
  res.status(410).json({ error: "autosave_only", detail: "Access policy changes are published by POST /api/admin/access-policies" });
}
