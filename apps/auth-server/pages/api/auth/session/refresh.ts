import type { NextApiRequest, NextApiResponse } from "next";

import { disableCaching, firstQueryValue, requestId, redirectError } from "../../../../src/server/http";
import { getUserBySessionToken, rotateSession, tokenFromRequest } from "../../../../src/server/session";
import { audit } from "../../../../src/server/audit";

function safeReturnTo(value: string | undefined): string {
  if (!value) return "/";
  if (value.startsWith("/") && !value.startsWith("//")) return value;
  try {
    const requested = new URL(value);
    const allowed = new URL(process.env.LETRON_ERP_APP_BASE_URL ?? "");
    return requested.origin === allowed.origin ? requested.toString() : "/";
  } catch {
    return "/";
  }
}

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    res.status(405).end();
    return;
  }
  try {
    const user = await getUserBySessionToken(tokenFromRequest(req));
    if (!user) {
      res.redirect(303, "/login");
      return;
    }
    await rotateSession(req, res, user.id);
    res.redirect(303, safeReturnTo(firstQueryValue(req.query.return_to)));
  } catch {
    await audit({ eventType: "session.refresh", outcome: "failure", requestId: requestId(req) }).catch(() => undefined);
    if (!res.headersSent) redirectError(res, "login_failed");
  }
}
