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

  const env = getEnv();
  const erpBaseUrl = env.FRAPPE_ERP_NEXT_URL;
  const syncSecret = env.LETRON_INTERNAL_API_SECRET || "";

  try {
    const response = await fetch(`${erpBaseUrl}/api/method/letron_api.operations.backup.scheduled_s3_backup`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Letron-Sync-Secret": syncSecret,
      },
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`ERP API error (${response.status}): ${errText}`);
    }

    const data = await response.json();
    res.status(200).json({
      ok: true,
      message: "Sao lưu thành công và đã tải lên AWS S3!",
      data: data.message || data,
    });
  } catch (error) {
    console.error("Failed to trigger backup:", error);
    res.status(500).json({
      error: "Không thể kích hoạt sao lưu",
      details: error instanceof Error ? error.message : String(error),
    });
  }
}
