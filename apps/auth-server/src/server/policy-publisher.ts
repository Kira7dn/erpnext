import { getEnv } from "./env";

export async function publishPolicyToErp(input: { policy: unknown; version: number; sha256: string }): Promise<void> {
  const env = getEnv();
  const baseUrl = env.LETRON_SSO_ERP_BASE_URL;
  const secret = env.LETRON_SSO_SYNC_SECRET ?? env.AUTH_ERP_SYNC_SECRET;
  if (!baseUrl || !secret) throw new Error("ERP policy publication is not configured");
  const response = await fetch(new URL("/api/method/letron_api.access_policy.publish", `${baseUrl}/`), {
    method: "POST",
    headers: { "content-type": "application/json", "X-Letron-Policy-Secret": secret },
    body: JSON.stringify(input),
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    const detail = body.replace(/\s+/g, " ").slice(0, 240);
    throw new Error(`ERP policy publication failed with HTTP ${response.status}${detail ? `: ${detail}` : ""}`);
  }
}
