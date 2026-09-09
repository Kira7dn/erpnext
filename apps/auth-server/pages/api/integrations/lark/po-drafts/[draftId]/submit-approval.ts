import type { NextApiRequest, NextApiResponse } from "next";

import { parsePoDraft, submitExistingPoDraftApproval } from "../../../../../../src/server/lark-purchase";
import { getUserBySessionToken, tokenFromRequest } from "../../../../../../src/server/session";
import { authenticateTestCredential } from "../../../../../../src/server/test-credential";
import { disableCaching } from "../../../../../../src/server/http";

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "POST") { res.setHeader("Allow", "POST"); res.status(405).end(); return; }
  const user = (await getUserBySessionToken(tokenFromRequest(req))) ?? (await authenticateTestCredential(req));
  if (!user) { res.status(401).json({ error: "authentication_required" }); return; }
  try {
    const draftId = String(req.query.draftId ?? "").trim();
    if (!draftId) { res.status(400).json({ error: "draft_id_required" }); return; }
    const input = parsePoDraft(req.body);
    const result = await submitExistingPoDraftApproval(draftId, input, user.email);
    res.status(result.idempotent ? 200 : 201).json({ status: "PENDING", ...result });
  } catch (error) {
    const message = error instanceof Error ? error.message : "approval_submission_failed";
    const status = message === "LARK_PO_INTEGRATION_NOT_CONFIGURED" ? 503 : message === "LARK_PO_SUBMISSION_IN_PROGRESS" ? 409 : 400;
    res.status(status).json({ error: message });
  }
}
