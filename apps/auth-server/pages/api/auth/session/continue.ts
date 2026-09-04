import type { NextApiRequest, NextApiResponse } from "next";

import { audit } from "../../../../src/server/audit";
import { disableCaching, redirectError, requestId } from "../../../../src/server/http";
import { finishInteraction } from "../../../../src/server/interaction";
import { getUserBySessionToken, rotateSession, tokenFromRequest } from "../../../../src/server/session";

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
    await finishInteraction(req, res, user.id);
  } catch {
    await audit({ eventType: "oidc.interaction", outcome: "failure", requestId: requestId(req) }).catch(() => undefined);
    if (!res.headersSent) redirectError(res, "interaction_failed");
  }
}
