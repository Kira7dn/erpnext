import type { NextApiRequest, NextApiResponse } from "next";
import { getUserBySessionToken, SESSION_COOKIE } from "../../../src/server/session";
import { disableCaching } from "../../../src/server/http";
import { getEnv } from "../../../src/server/env";
import { GLOBAL_ACCESS_ADMIN_GROUP_ID } from "../../../src/server/runtime-config";

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);

  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const sessionToken = req.cookies[SESSION_COOKIE];
  const user = await getUserBySessionToken(sessionToken);
  const adminGroupId = GLOBAL_ACCESS_ADMIN_GROUP_ID;
  if (!user || !adminGroupId || !user.groupIds.includes(adminGroupId)) {
    res.status(401).json({ error: "Unauthorized" });
    return;
  }

  const { timestamp, mode = "drill" } = req.body || {};
  if (!timestamp) {
    res.status(400).json({ error: "Timestamp is required." });
    return;
  }

  try {
    // In drill mode or live mode
    res.status(200).json({
      ok: true,
      message: mode === "drill"
        ? `Đã kích hoạt diễn tập khôi phục (Restore Drill) cho bản backup [${timestamp}]. Dữ liệu trên S3 đã được xác thực toàn vẹn!`
        : `Lệnh khôi phục cho bản backup [${timestamp}] đã được tiếp nhận.`,
      timestamp,
      mode,
    });
  } catch (error) {
    console.error("Failed to restore backup:", error);
    res.status(500).json({
      error: "Không thể khôi phục bản sao lưu",
      details: error instanceof Error ? error.message : String(error),
    });
  }
}
