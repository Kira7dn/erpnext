import { timingSafeEqual } from "node:crypto";
import type { NextApiRequest, NextApiResponse } from "next";

import { getEnv } from "../../../../../src/server/env";
import { disableCaching } from "../../../../../src/server/http";
import { buildPoDraftFromCorrelation, submitPoDraftApproval } from "../../../../../src/server/lark-purchase";
import { supplierPortalConfig } from "../../../../../src/server/supplier-portal-config";

type Body = {
  orchestration_id?: unknown;
  selected_supplier_quotation_name?: unknown;
  justification?: unknown;
};

function authorized(req: NextApiRequest): boolean {
  const env = getEnv();
  const secret = env.LETRON_SUPPLIER_PORTAL_SECRET ?? env.LETRON_SSO_SYNC_SECRET;
  const value = String(req.headers.authorization ?? "");
  if (!secret || !/^Bearer\s+\S+$/i.test(value)) return false;
  const supplied = Buffer.from(value.replace(/^Bearer\s+/i, ""), "utf8");
  const expected = Buffer.from(secret, "utf8");
  return supplied.length === expected.length && timingSafeEqual(supplied, expected);
}

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "POST") { res.setHeader("Allow", "POST"); res.status(405).end(); return; }
  if (!authorized(req)) { res.status(401).json({ error: "supplier_portal_service_unauthorized" }); return; }
  const body = (req.body ?? {}) as Body;
  const orchestrationId = String(body.orchestration_id ?? "").trim();
  const selected = String(body.selected_supplier_quotation_name ?? "").trim();
  if (!orchestrationId || !selected) { res.status(400).json({ error: "approval_correlation_incomplete" }); return; }
  const config = supplierPortalConfig();
  if (!config.approval_submitter_email) { res.status(503).json({ error: "supplier_portal_submitter_not_configured" }); return; }
  try {
    const input = await buildPoDraftFromCorrelation({
      orchestrationId,
      supplierQuotationName: selected,
      justification: String(body.justification ?? ""),
      portalUrl: `${config.next_base_url}/supplier`,
      cookieHeader: "",
    });
    const result = await submitPoDraftApproval(input, config.approval_submitter_email);
    res.status(result.idempotent ? 200 : 201).json({ status: "PENDING", ...result });
  } catch (error) {
    const message = error instanceof Error ? error.message : "supplier_portal_approval_failed";
    res.status(message === "LARK_PO_INTEGRATION_NOT_CONFIGURED" ? 503 : 400).json({ error: message });
  }
}
