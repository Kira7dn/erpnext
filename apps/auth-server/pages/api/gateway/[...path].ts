import { createHash, createHmac, randomUUID } from "node:crypto";

import type { NextApiRequest, NextApiResponse } from "next";

import {
  getUserBySessionToken,
  getUserByGatewaySessionToken,
  tokenFromRequest,
} from "../../../src/server/session";
import { getEnv } from "../../../src/server/env";
import { getPublishedPolicy } from "../../../src/server/published-policy";
import {
  canAccessPolicy,
  policyRolesForGroups,
  routeOperation,
} from "../../../src/server/access-policy";
import { audit } from "../../../src/server/audit";
import { disableCaching } from "../../../src/server/http";
import { authenticateTestCredential } from "../../../src/server/test-credential";
import { syncLarkGroupsIfStale } from "../../../src/server/users";

export const config = { api: { bodyParser: false } };

function duration(start: number): number {
  return Number((performance.now() - start).toFixed(1));
}

function errorResponse(
  res: NextApiResponse,
  status: number,
  code: string,
  message: string,
  retryable = status === 429 || status >= 500,
): void {
  res.status(status).json({ error: code, message, retryable });
}

function body(req: NextApiRequest): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer | string) =>
      chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)),
    );
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function forwardedHeaders(
  req: NextApiRequest,
  user: {
    id: string;
    email: string;
    tenantKey: string | null;
    subject: string | null;
    subjectType: string | null;
  },
  version: number,
  path: string,
  roles: string[],
  secret: string,
  query: string,
  bodyHash: string,
): Record<string, string> {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const expires = String(Number(timestamp) + 60);
  const method = req.method ?? "GET";
  const requestId = randomUUID();
  const encodedRoles = Buffer.from(JSON.stringify(roles), "utf8").toString(
    "base64url",
  );
  const payload = `${timestamp}.${expires}.${method}.${path}.${query}.${bodyHash}.${user.id}.${user.email}.${user.tenantKey ?? ""}.${user.subject ?? ""}.${user.subjectType ?? ""}.${version}.${encodedRoles}.${requestId}`;
  const signature = createHmac("sha256", secret).update(payload).digest("hex");
  const headers: Record<string, string> = {
    "X-Letron-Gateway-Timestamp": timestamp,
    "X-Letron-Gateway-User": user.id,
    "X-Letron-Gateway-Email": user.email,
    "X-Letron-Gateway-Tenant": user.tenantKey ?? "",
    "X-Letron-Gateway-Subject": user.subject ?? "",
    "X-Letron-Gateway-Subject-Type": user.subjectType ?? "",
    "X-Letron-Gateway-Method": method,
    "X-Letron-Gateway-Path": path,
    "X-Letron-Gateway-Policy-Version": String(version),
    "X-Letron-Gateway-Roles": encodedRoles,
    "X-Letron-Gateway-Issued-At": timestamp,
    "X-Letron-Gateway-Expires-At": expires,
    "X-Letron-Gateway-Request-Id": requestId,
    "X-Letron-Gateway-Query": query,
    "X-Letron-Gateway-Body-Sha256": bodyHash,
    "X-Letron-Gateway-Signature": signature,
  };
  const authorization = req.headers.authorization;
  if (typeof authorization === "string") headers.Authorization = authorization;
  const contentType = req.headers["content-type"];
  if (typeof contentType === "string") headers["Content-Type"] = contentType;
  const idempotencyKey = req.headers["x-idempotency-key"];
  if (typeof idempotencyKey === "string") {
    headers["X-Idempotency-Key"] = idempotencyKey.slice(0, 128);
  }
  return headers;
}

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse,
): Promise<void> {
  const startedAt = performance.now();
  const timings: Record<string, number> = {};
  const finish = () => {
    timings.gateway_total = duration(startedAt);
    res.setHeader(
      "Server-Timing",
      Object.entries(timings)
        .map(([name, value]) => `${name};dur=${value}`)
        .join(", "),
    );
  };
  disableCaching(res);
  const sessionStartedAt = performance.now();
  const bffSession = typeof req.headers["x-letron-bff-session"] === "string"
    ? req.headers["x-letron-bff-session"]
    : undefined;
  let user = (await getUserByGatewaySessionToken(bffSession))
    ?? (await getUserBySessionToken(tokenFromRequest(req)))
    ?? (await authenticateTestCredential(req));
  timings.session = duration(sessionStartedAt);
  if (!user) {
    finish();
    errorResponse(res, 401, "authentication_required", "Authentication is required.");
    return;
  }
  if (bffSession) {
    try {
      const groupIds = await syncLarkGroupsIfStale(user.id);
      user = { ...user, groupIds };
    } catch {
      finish();
      errorResponse(res, 503, "authorization_unavailable", "Authorization state is temporarily unavailable.");
      return;
    }
  }
  const policyStartedAt = performance.now();
  const policy = await getPublishedPolicy();
  timings.policy = duration(policyStartedAt);
  if (!policy) {
    finish();
    errorResponse(res, 503, "access_policy_not_published", "Access policy is not available.");
    return;
  }
  const path = `/${Array.isArray(req.query.path) ? req.query.path.join("/") : String(req.query.path ?? "")}`;
  const operation = routeOperation(req.method ?? "GET", path);
  if (!operation || !canAccessPolicy(policy.policy, user.groupIds, operation)) {
    await audit({
      eventType: "gateway.authorization",
      outcome: "failure",
      userId: user.id,
      detail: { path, reason: "policy_denied", policy_version: policy.version },
    }).catch(() => undefined);
    finish();
    errorResponse(res, 403, "access_denied", "Access to this resource is denied.");
    return;
  }
  const env = getEnv();
  const baseUrl = env.FRAPPE_ERP_NEXT_URL;
  const secret = env.LETRON_INTERNAL_API_SECRET;
  if (!baseUrl || !secret) {
    finish();
    errorResponse(res, 503, "gateway_not_configured", "Gateway is not configured.");
    return;
  }
  const roles = policyRolesForGroups(policy.policy, user.groupIds);
  const target = new URL(path, `${baseUrl}/`);
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(req.query)) {
    if (key === "path") continue;
    for (const item of Array.isArray(value) ? value : [value])
      if (item !== undefined) query.append(key, item);
  }
  target.search = query.toString();
  const requestBody = ["GET", "HEAD"].includes(req.method ?? "GET") ? undefined : await body(req);
  const bodyHash = requestBody ? createHash("sha256").update(requestBody).digest("hex") : "";
  let response: Response;
  const erpStartedAt = performance.now();
  try {
    response = await fetch(target, {
      method: req.method,
      headers: forwardedHeaders(req, user, policy.version, path, roles, secret, target.search, bodyHash),
      body: requestBody as unknown as BodyInit,
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    timings.erp_fetch = duration(erpStartedAt);
    finish();
    errorResponse(res, 502, "erp_gateway_unavailable", "ERP service is unavailable.", true);
    return;
  }
  timings.erp_fetch = duration(erpStartedAt);
  res.status(response.status);
  response.headers.forEach((value, key) => {
    if (
      ![
        "connection",
        "content-encoding",
        "content-length",
        "transfer-encoding",
        "server-timing",
      ].includes(key)
    )
      res.setHeader(key, value);
  });
  finish();
  if (!response.body) {
    res.end();
    return;
  }
  const reader = response.body.getReader();
  try {
    for (;;) {
      const chunk = await reader.read();
      if (chunk.done) break;
      res.write(Buffer.from(chunk.value));
    }
  } finally {
    reader.releaseLock();
  }
  res.end();
}
