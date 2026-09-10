import type { NextApiRequest, NextApiResponse } from "next";

import { getEnv } from "../../../../src/server/env";
import { sendLarkMail } from "../../../../src/server/lark-mail";

function authorized(req: NextApiRequest): boolean {
  const expected = getEnv().LETRON_API_KEY;
  const supplied = req.headers.authorization?.replace(/^Bearer\s+/i, "") ?? "";
  return Boolean(expected && supplied && supplied === expected);
}

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  if (req.method !== "POST" || !authorized(req)) { res.status(401).json({ error: "unauthorized" }); return; }
  try {
    const body = req.body as { to?: string; subject?: string; body_html?: string; body_plain_text?: string };
    if (!body.to || !body.subject || !body.body_html) { res.status(400).json({ error: "to_subject_body_required" }); return; }
    res.status(200).json({ data: await sendLarkMail({ to: body.to, subject: body.subject, bodyHtml: body.body_html, bodyPlainText: body.body_plain_text }) });
  } catch { res.status(502).json({ error: "lark_mail_send_failed" }); }
}
