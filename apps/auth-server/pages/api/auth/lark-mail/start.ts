import type { NextApiRequest, NextApiResponse } from "next";

import { getDb } from "../../../../src/server/db";
import { randomToken, sha256 } from "../../../../src/server/crypto";
import { appendSetCookie, disableCaching, requestIsSecure, serializeCookie } from "../../../../src/server/http";
import { buildLarkMailAuthorizationUrl, LARK_MAIL_OAUTH_COOKIE, LARK_MAIL_OAUTH_TTL_SECONDS } from "../../../../src/server/lark-mail";

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "GET") { res.setHeader("Allow", "GET"); res.status(405).end(); return; }
  const state = randomToken();
  const browserBinding = randomToken();
  await getDb().larkMailOAuthTransaction.create({
    data: {
      stateHash: sha256(state),
      browserBindingHash: sha256(browserBinding),
      expiresAt: new Date(Date.now() + LARK_MAIL_OAUTH_TTL_SECONDS * 1000),
    },
  });
  appendSetCookie(res, serializeCookie(LARK_MAIL_OAUTH_COOKIE, browserBinding, { maxAge: LARK_MAIL_OAUTH_TTL_SECONDS, secure: requestIsSecure(req) }));
  res.redirect(303, buildLarkMailAuthorizationUrl(state).toString());
}
