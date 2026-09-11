import { timingSafeEqual } from "node:crypto";
import type { NextApiRequest, NextApiResponse } from "next";

import { getEnv } from "../../../../src/server/env";
import { revokeErpGatewaySession } from "../../../../src/server/erp-handoff";
import { disableCaching } from "../../../../src/server/http";

function authorized(req: NextApiRequest, secret: string): boolean {
  const supplied = req.headers.authorization?.replace(/^Bearer\s+/i, "") ?? "";
  const left = Buffer.from(supplied);
  const right = Buffer.from(secret);
  return left.length === right.length && timingSafeEqual(left, right);
}

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "POST") { res.setHeader("Allow", "POST"); res.status(405).end(); return; }
  const env = getEnv();
  if (!env.LETRON_INTERNAL_API_SECRET || !authorized(req, env.LETRON_INTERNAL_API_SECRET)) { res.status(401).json({ error: "unauthorized" }); return; }
  const token = typeof req.body?.gateway_session === "string" ? req.body.gateway_session : "";
  if (!token) { res.status(400).json({ error: "gateway_session_required" }); return; }
  await revokeErpGatewaySession(token);
  res.status(204).end();
}
