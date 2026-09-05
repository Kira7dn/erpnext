import type { NextApiRequest, NextApiResponse } from "next";

import { adminUser, isJsonRequest } from "../../../../src/server/admin";
import { audit } from "../../../../src/server/audit";
import { disableCaching } from "../../../../src/server/http";
import { fetchLarkGroupCatalog } from "../../../../src/server/lark";
import { openApiPermissions } from "../../../../src/server/openapi-catalog";

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "GET" || !isJsonRequest(req)) { res.status(req.method === "GET" ? 406 : 405).json({ error: req.method === "GET" ? "json_required" : "method_not_allowed" }); return; }
  const actor = await adminUser(req);
  if (!actor) { res.status(403).json({ error: "global_access_admin_required" }); return; }
  try {
    const groups = await fetchLarkGroupCatalog();
    const permissions = openApiPermissions();
    await audit({ eventType: "access_catalog.loaded", outcome: "success", userId: actor.id, detail: { lark_groups: groups.length, openapi_permissions: permissions.length } });
    res.status(200).json({ groups, permissions });
  } catch (error) {
    await audit({ eventType: "access_catalog.loaded", outcome: "failure", userId: actor.id, detail: { reason: error instanceof Error ? error.message : "catalog_failed" } }).catch(() => undefined);
    res.status(200).json({ groups: [], permissions: [], catalogError: "Không lấy được danh sách Lark User Group; kiểm tra quyền của Lark app." });
  }
}
