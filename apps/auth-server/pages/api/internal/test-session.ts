import type { NextApiRequest, NextApiResponse } from "next";

import { audit } from "../../../src/server/audit";
import { createErpHandoff, consumeErpHandoff, type AppKey } from "../../../src/server/erp-handoff";
import { disableCaching } from "../../../src/server/http";
import { createSession, setSessionCookie } from "../../../src/server/session";
import { authenticateTestCredential } from "../../../src/server/test-credential";

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    res.status(405).json({ error: "method_not_allowed" });
    return;
  }

  const user = await authenticateTestCredential(req);
  if (!user) {
    res.status(401).json({ error: "test_credential_invalid" });
    return;
  }

  const session = await createSession(user.id);
  setSessionCookie(req, res, session.token, session.expiresAt);
  const requestedApp = typeof req.body?.app === "string" ? req.body.app : "";
  const app = ["assets", "purchase", "accounts"].includes(requestedApp)
    ? requestedApp as AppKey
    : null;
  let appSession: { token: string; expiresAt: Date } | null = null;
  if (app) {
    const handoff = await createErpHandoff(user.id, app);
    const consumed = await consumeErpHandoff(handoff.code, app);
    if (!consumed) {
      res.status(503).json({ error: "test_app_session_unavailable" });
      return;
    }
    appSession = { token: consumed.gatewayToken, expiresAt: consumed.gatewayExpiresAt };
  }
  await audit({
    eventType: "test.session",
    outcome: "success",
    userId: user.id,
    detail: { auth_method: "configured_test_credential", ...(app ? { app } : {}) },
  });
  res.status(200).json({
    data: {
      user: {
        email: user.email,
        displayName: user.displayName,
        avatarUrl: user.avatarUrl,
      },
      expires_at: session.expiresAt.toISOString(),
      ...(appSession ? {
        app,
        app_session: appSession.token,
        app_session_expires_at: appSession.expiresAt.toISOString(),
      } : {}),
    },
  });
}
