import { timingSafeEqual } from "node:crypto";

import type { NextApiRequest, NextApiResponse } from "next";

import { getEnv } from "../../../../../src/server/env";
import { disableCaching } from "../../../../../src/server/http";
import { approvePoDraftApproval } from "../../../../../src/server/lark-purchase";

function authorized(req: NextApiRequest): boolean {
  const expected = getEnv().LETRON_API_KEY;
  const supplied = String(req.headers.authorization ?? "").replace(/^Bearer\s+/i, "");
  if (!expected || !supplied) return false;
  const left = Buffer.from(supplied, "utf8");
  const right = Buffer.from(expected, "utf8");
  return left.length === right.length && timingSafeEqual(left, right);
}

type Body = { instance_code?: unknown };

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    res.status(405).end();
    return;
  }
  if (getEnv().NODE_ENV === "production") {
    res.status(403).json({ error: "real_test_auto_approve_disabled_in_production" });
    return;
  }
  if (!authorized(req)) {
    res.status(401).json({ error: "internal_unauthorized" });
    return;
  }
  const instanceCode = String((req.body as Body | undefined)?.instance_code ?? "").trim();
  if (!instanceCode) {
    res.status(400).json({ error: "instance_code_required" });
    return;
  }
  try {
    res.status(200).json(await approvePoDraftApproval(instanceCode));
  } catch (error) {
    const message = error instanceof Error ? error.message : "lark_approval_auto_approve_failed";
    res.status(400).json({ error: message });
  }
}
