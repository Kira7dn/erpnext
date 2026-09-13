import { createHmac, randomUUID } from "node:crypto";
import { getEnv } from "./env";
import { invalidatePolicyCache } from "./cache";
import { registryMetadata } from "./openapi-catalog";

export async function publishPolicyToErp(input: { policy: unknown; version: number; sha256: string }): Promise<void> {
  const env = getEnv();
  const baseUrl = env.FRAPPE_ERP_NEXT_URL;
  const secret = env.LETRON_INTERNAL_API_SECRET;
  if (!secret) throw new Error("ERP policy publication is not configured");
  const path = "/api/method/letron_api.control.access_policy.publish";
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const expires = String(Number(timestamp) + 60);
  const requestId = randomUUID();
  const registry = registryMetadata();
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
    body: JSON.stringify({ ...input, registry_version: registry.version, registry_sha256: registry.sha256 }),
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    const detail = body.replace(/\s+/g, " ").slice(0, 240);
    throw new Error(`ERP policy publication failed with HTTP ${response.status}${detail ? `: ${detail}` : ""}`);
  }
  const payload = await response.json().catch(() => null) as { message?: Record<string, unknown> } | null;
  const result = (payload?.message ?? payload) as Record<string, unknown> | null;
  if (
    !result ||
    result.ok !== true ||
    result.projection_ok !== true ||
    result.version !== input.version ||
    result.sha256 !== input.sha256
    || result.registry_version !== registry.version
    || result.registry_sha256 !== registry.sha256
  ) {
    throw new Error("ERP policy publication returned an unverified projection");
  }
  await invalidatePolicyCache();
}
