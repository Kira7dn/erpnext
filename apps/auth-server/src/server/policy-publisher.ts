import { createHmac, randomUUID } from "node:crypto";
import { getEnv } from "./env";
import { invalidatePolicyCache } from "./cache";

export async function publishPolicyToErp(input: { policy: unknown; version: number; sha256: string }): Promise<void> {
  const env = getEnv();
  const baseUrl = env.LETRON_SSO_ERP_BASE_URL;
  const secret = env.LETRON_SSO_SYNC_SECRET;
  if (!baseUrl || !secret) throw new Error("ERP policy publication is not configured");
  const path = "/api/method/letron_api.control.access_policy.publish";
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const expires = String(Number(timestamp) + 60);
  const requestId = randomUUID();
  const signature = createHmac("sha256", secret).update(`${timestamp}.${expires}.POST.${path}.${requestId}`).digest("hex");
  const response = await fetch(new URL(path, `${baseUrl}/`), {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "X-Letron-Control-Timestamp": timestamp,
      "X-Letron-Control-Expires-At": expires,
      "X-Letron-Control-Request-Id": requestId,
      "X-Letron-Control-Signature": signature,
    },
    body: JSON.stringify(input),
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    const detail = body.replace(/\s+/g, " ").slice(0, 240);
    throw new Error(`ERP policy publication failed with HTTP ${response.status}${detail ? `: ${detail}` : ""}`);
  }
  await invalidatePolicyCache();
}
