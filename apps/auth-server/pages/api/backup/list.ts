import type { NextApiRequest, NextApiResponse } from "next";
import { getUserBySessionToken, SESSION_COOKIE } from "../../../src/server/session";
import { disableCaching } from "../../../src/server/http";
import { listPaginatedBackups } from "../../../src/server/backup-service";

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);

  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const sessionToken = req.cookies[SESSION_COOKIE];
  const user = await getUserBySessionToken(sessionToken);
  if (!user) {
    res.status(401).json({ error: "Unauthorized" });
    return;
  }

  try {
    const limit = req.query.limit ? parseInt(String(req.query.limit), 10) : 8;
    const cursor = req.query.cursor ? String(req.query.cursor) : undefined;
    const from = req.query.from ? String(req.query.from) : undefined;
    const to = req.query.to ? String(req.query.to) : undefined;
    const search = req.query.search ? String(req.query.search) : undefined;

    const result = await listPaginatedBackups({
      limit,
      cursor,
      from,
      to,
      search,
    });

    res.status(200).json(result);
  } catch (error) {
    console.error("Failed to list S3 backups:", error);
    res.status(500).json({
      error: "Failed to fetch backups from S3",
      details: error instanceof Error ? error.message : String(error),
    });
  }
}
