import type { NextApiRequest, NextApiResponse } from "next";

import { audit } from "../../../src/server/audit";
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
  await audit({
    eventType: "test.session",
    outcome: "success",
    userId: user.id,
    detail: { auth_method: "configured_test_credential" },
  });
  res.status(200).json({
    data: {
      user: {
        email: user.email,
        displayName: user.displayName,
        avatarUrl: user.avatarUrl,
      },
      expires_at: session.expiresAt.toISOString(),
    },
  });
}
