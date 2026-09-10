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
    const body = req.body as { to?: string; subject?: string; body_html?: string; body_plain_text?: string; idempotency_key?: string };
    const idempotencyKey = String(body.idempotency_key ?? req.headers["x-idempotency-key"] ?? "").trim();
    if (!body.to || !body.subject || !body.body_html || !idempotencyKey) { res.status(400).json({ error: "to_subject_body_idempotency_required" }); return; }
    res.status(200).json({ data: await sendLarkMail({ to: body.to, subject: body.subject, bodyHtml: body.body_html, bodyPlainText: body.body_plain_text, idempotencyKey }) });
  } catch (error) {
    const code = error instanceof Error && error.message === "LARK_MAIL_SEND_IN_PROGRESS" ? "lark_mail_send_in_progress" : "lark_mail_send_failed";
    const providerCode = error instanceof Error ? error.message.split(":", 1)[0].slice(0, 80) : "";
    res.status(code === "lark_mail_send_in_progress" ? 409 : 502).json({ error: code, provider_code: providerCode || undefined });
  }
}
