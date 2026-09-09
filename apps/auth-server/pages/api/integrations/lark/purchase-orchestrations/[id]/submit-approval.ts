import type { NextApiRequest, NextApiResponse } from "next";

import { disableCaching } from "../../../../../../src/server/http";
import { getUserBySessionToken, tokenFromRequest } from "../../../../../../src/server/session";
import { authenticateTestCredential } from "../../../../../../src/server/test-credential";
import {
  buildPoDraftFromCorrelation,
  submitPoDraftApproval,
} from "../../../../../../src/server/lark-purchase";

type Body = { justification?: unknown };

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    res.status(405).end();
    return;
  }
  const user = (await getUserBySessionToken(tokenFromRequest(req))) ?? (await authenticateTestCredential(req));
  if (!user) {
    res.status(401).json({ error: "authentication_required" });
    return;
  }
  const orchestrationId = String(req.query.id ?? "").trim();
  const body = (req.body ?? {}) as Body;
  if (!orchestrationId) {
    res.status(400).json({ error: "orchestration_id_required" });
    return;
  }
  try {
    const input = await buildPoDraftFromCorrelation({
      orchestrationId,
      supplierQuotationName: undefined,
      justification: String(body.justification ?? ""),
      cookieHeader: req.headers.cookie ?? req.headers.authorization ?? "",
    });
    const result = await submitPoDraftApproval(input, user.email);
    res.status(result.idempotent ? 200 : 201).json({ status: "PENDING", ...result });
  } catch (error) {
    const message = error instanceof Error ? error.message : "approval_submission_failed";
    const status = message === "LARK_PO_INTEGRATION_NOT_CONFIGURED" || message === "ERP_APPROVED_PO_NOT_CONFIGURED"
      ? 503
      : message === "LARK_PO_SUBMISSION_IN_PROGRESS"
        ? 409
        : message.startsWith("ERP_SOURCE_READ_FAILED_")
          ? 502
          : 400;
    res.status(status).json({ error: message });
  }
}
