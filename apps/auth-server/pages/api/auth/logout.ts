import type { NextApiRequest, NextApiResponse } from "next";

import { audit } from "../../../src/server/audit";
import { disableCaching } from "../../../src/server/http";
import { clearSessionCookie, revokeRequestSession } from "../../../src/server/session";

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    res.status(405).end();
    return;
  }
  await revokeRequestSession(req);
  clearSessionCookie(res);
  await audit({ eventType: "session.logout", outcome: "success" }).catch(() => undefined);
  res.redirect(303, "/api/oidc/session/end");
}
