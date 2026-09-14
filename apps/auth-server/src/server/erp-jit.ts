import { createHmac, randomUUID } from "node:crypto";

import { getEnv } from "./env";

type JitUser = {
  email: string;
  displayName: string;
  identities: Array<{ tenantKey: string; subject: string; subjectType: string | null }>;
};

export async function ensureErpIdentity(user: JitUser): Promise<void> {
  const identity = user.identities.find((item) => item.subjectType === "union_id");
  const env = getEnv();
  if (!identity) throw new Error("ERP_JIT_IDENTITY_MISSING");
  const path = "/api/method/letron_api.auth.sso_identity.provision_identity";
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const expires = String(Number(timestamp) + 60);
  const requestId = randomUUID();
  const signature = createHmac("sha256", env.LETRON_AUTH_TO_ERP_JIT_SECRET)
    .update(`${timestamp}.${expires}.POST.${path}.${requestId}`)
    .digest("hex");
  const csrfResponse = await fetch(new URL("/api/method/letron_api.auth.gateway.csrf_token", `${env.FRAPPE_ERP_NEXT_URL}/`), {
    headers: { accept: "application/json" },
    signal: AbortSignal.timeout(15_000),
  });
  const setCookies = typeof csrfResponse.headers.getSetCookie === "function"
    ? csrfResponse.headers.getSetCookie()
    : [];
  const cookies = [
    "sid=Guest",
    "system_user=no",
    "full_name=Guest",
    "user_id=Guest",
    "user_lang=vi",
    ...setCookies.map((value) => value.split(";", 1)[0]).filter((value) => !value.startsWith("sid=")),
  ].join("; ");
  const csrfPayload = await csrfResponse.json().catch(() => null) as { message?: string } | null;
  const csrf = csrfPayload?.message;
  if (!csrfResponse.ok || typeof csrf !== "string" || !csrf) throw new Error("ERP_JIT_CSRF_UNAVAILABLE");
  const response = await fetch(new URL(path, `${env.FRAPPE_ERP_NEXT_URL}/`), {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "X-Letron-JIT-Timestamp": timestamp,
      "X-Letron-JIT-Expires-At": expires,
      "X-Letron-JIT-Request-Id": requestId,
      "X-Letron-JIT-Signature": signature,
      "X-Frappe-CSRF-Token": csrf,
      cookie: cookies,
    },
    body: JSON.stringify({
      tenant_key: identity.tenantKey,
      subject: identity.subject,
      subject_type: identity.subjectType,
      email: user.email,
      display_name: user.displayName,
    }),
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) {
    const detail = (await response.text().catch(() => "")).replace(/\s+/g, " ").slice(0, 900);
    throw new Error(`ERP_JIT_FAILED_${response.status}${detail ? `_${detail}` : ""}`);
  }
  const payload = await response.json().catch(() => null) as { message?: { ok?: boolean } } | null;
  if (payload?.message?.ok !== true) throw new Error("ERP_JIT_UNVERIFIED");
}
