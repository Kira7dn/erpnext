import type { NextApiRequest, NextApiResponse } from "next";

import { latestLarkMail } from "../../../../src/server/lark-mail";
import { getEnv } from "../../../../src/server/env";

function authorized(req: NextApiRequest): boolean {
  const expected = getEnv().LETRON_API_KEY;
  const supplied = req.headers.authorization?.replace(/^Bearer\s+/i, "") ?? "";
  return Boolean(expected && supplied && supplied === expected);
}

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  if (req.method !== "GET" || !authorized(req)) { res.status(401).json({ error: "unauthorized" }); return; }
  try {
    const subject = typeof req.query.subject === "string" ? req.query.subject : "";
    const after = typeof req.query.after === "string" ? req.query.after : undefined;
    const messageId = typeof req.query.message_id === "string" ? req.query.message_id : undefined;
    if (!subject) { res.status(400).json({ error: "subject_required" }); return; }
    res.status(200).json({ data: await latestLarkMail({ subject, after, messageId }) });
  } catch { res.status(502).json({ error: "lark_mail_read_failed" }); }
}
