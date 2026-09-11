import { timingSafeEqual } from "node:crypto";
import type { NextApiRequest, NextApiResponse } from "next";
import { z } from "zod";

import { getEnv } from "../../../../src/server/env";
import { consumeErpHandoff, type AppKey } from "../../../../src/server/erp-handoff";
import { disableCaching } from "../../../../src/server/http";

const inputSchema = z.object({ code: z.string().min(32).max(256), app: z.enum(["assets", "purchase", "accounts"]) }).strict();
function authorized(req: NextApiRequest, secret: string): boolean {
  const supplied = req.headers.authorization?.replace(/^Bearer\s+/i, "") ?? "";
  const left = Buffer.from(supplied); const right = Buffer.from(secret);
  return left.length === right.length && timingSafeEqual(left, right);
}
export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "POST") { res.setHeader("Allow", "POST"); res.status(405).end(); return; }
  const env = getEnv();
  if (!env.LETRON_INTERNAL_API_SECRET || !authorized(req, env.LETRON_INTERNAL_API_SECRET)) { res.status(401).json({ error: "unauthorized" }); return; }
  const parsed = inputSchema.safeParse(req.body);
  if (!parsed.success) { res.status(400).json({ error: "invalid_grant" }); return; }
  const result = await consumeErpHandoff(parsed.data.code, parsed.data.app as AppKey);
  if (!result) { res.status(401).json({ error: "grant_expired_or_consumed" }); return; }
  res.status(200).json({ session: result.gatewayToken, expires_at: result.gatewayExpiresAt.toISOString(), user: result.user });
}
