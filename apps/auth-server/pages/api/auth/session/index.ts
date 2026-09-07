import type { NextApiRequest, NextApiResponse } from "next";

import { disableCaching } from "../../../../src/server/http";
import { getUserBySessionToken, tokenFromRequest } from "../../../../src/server/session";

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    res.status(405).json({ error: "method_not_allowed" });
    return;
  }
  const user = await getUserBySessionToken(tokenFromRequest(req));
  if (!user) {
    res.status(401).json({ error: "authentication_required" });
    return;
  }
  res.status(200).json({
    user: {
      email: user.email,
      displayName: user.displayName,
      avatarUrl: user.avatarUrl,
    },
  });
}
