import type { NextApiRequest, NextApiResponse } from "next";

import { audit } from "../../../../src/server/audit";
import { firstQueryValue, parseCookies, appendSetCookie, disableCaching, requestIsSecure, serializeCookie } from "../../../../src/server/http";
import { completeLarkMailOAuth, LARK_MAIL_OAUTH_COOKIE } from "../../../../src/server/lark-mail";

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "GET") { res.setHeader("Allow", "GET"); res.status(405).end(); return; }
  const state = firstQueryValue(req.query.state);
  const code = firstQueryValue(req.query.code);
  const binding = parseCookies(req.headers.cookie)[LARK_MAIL_OAUTH_COOKIE];
  if (!state || !code || !binding) { res.status(400).json({ error: "mail_oauth_callback_rejected" }); return; }
  try {
    const expectedMailbox = await completeLarkMailOAuth({ state, binding, code });
    appendSetCookie(res, serializeCookie(LARK_MAIL_OAUTH_COOKIE, "", { maxAge: 0, expires: new Date(0), secure: requestIsSecure(req) }));
    await audit({ eventType: "lark.mail_oauth", outcome: "success", detail: { mailbox: expectedMailbox } });
    res.status(200).json({ ok: true, mailbox: expectedMailbox, message: "Lark Mail authorization stored" });
  } catch (error) {
    await audit({ eventType: "lark.mail_oauth", outcome: "failure", detail: { reason: error instanceof Error ? error.message.slice(0, 80) : "unknown" } }).catch(() => undefined);
    res.status(400).json({ error: "mail_oauth_failed" });
  }
}
