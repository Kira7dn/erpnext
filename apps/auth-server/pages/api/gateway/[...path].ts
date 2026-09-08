import { createHmac, randomUUID } from "node:crypto";

import type { NextApiRequest, NextApiResponse } from "next";

import { getUserBySessionToken, tokenFromRequest } from "../../../src/server/session";
import { syncLarkGroupsIfStale } from "../../../src/server/users";
import { getEnv } from "../../../src/server/env";
import { getPublishedPolicy } from "../../../src/server/published-policy";
import { canAccessPolicy, policyRolesForGroups, routeOperation } from "../../../src/server/access-policy";
import { audit } from "../../../src/server/audit";
import { disableCaching } from "../../../src/server/http";

export const config = { api: { bodyParser: false } };

function duration(start: number): number { return Number((performance.now() - start).toFixed(1)); }

function body(req: NextApiRequest): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer | string) => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function forwardedHeaders(req: NextApiRequest, user: { id: string; email: string; tenantKey: string | null; subject: string | null; subjectType: string | null }, version: number, path: string, roles: string[], secret: string): Record<string, string> {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const expires = String(Number(timestamp) + 60);
  const method = req.method ?? "GET";
  const requestId = (typeof req.headers["x-request-id"] === "string" && req.headers["x-request-id"].slice(0, 128)) || randomUUID();
  const encodedRoles = Buffer.from(JSON.stringify(roles), "utf8").toString("base64url");
  const payload = `${timestamp}.${expires}.${method}.${path}.${user.id}.${user.email}.${user.tenantKey ?? ""}.${user.subject ?? ""}.${user.subjectType ?? ""}.${version}.${encodedRoles}.${requestId}`;
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
    "X-Letron-Gateway-Signature": signature,
  };
  const authorization = req.headers.authorization;
  if (typeof authorization === "string") headers.Authorization = authorization;
  const contentType = req.headers["content-type"];
  if (typeof contentType === "string") headers["Content-Type"] = contentType;
  return headers;
}

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  const startedAt = performance.now();
  const timings: Record<string, number> = {};
  const finish = () => {
    timings.gateway_total = duration(startedAt);
    res.setHeader("Server-Timing", Object.entries(timings).map(([name, value]) => `${name};dur=${value}`).join(", "));
  };
  disableCaching(res);
  const sessionStartedAt = performance.now();
  let user = await getUserBySessionToken(tokenFromRequest(req));
  timings.session = duration(sessionStartedAt);
  if (!user) { finish(); res.status(401).json({ error: "authentication_required" }); return; }
  if (getEnv().LARK_GROUP_SYNC_ENABLED) {
    const larkStartedAt = performance.now();
    try {
      user = { ...user, groupIds: await syncLarkGroupsIfStale(user.id) };
    } catch {
      timings.lark_sync = duration(larkStartedAt);
      finish();
      res.status(503).json({ error: "access_policy_unavailable" });
      return;
    }
    timings.lark_sync = duration(larkStartedAt);
    if (!user) { finish(); res.status(401).json({ error: "authentication_required" }); return; }
  }
  const policyStartedAt = performance.now();
  const policy = await getPublishedPolicy();
  timings.policy = duration(policyStartedAt);
  if (!policy) { finish(); res.status(503).json({ error: "access_policy_not_published" }); return; }
  const path = `/${Array.isArray(req.query.path) ? req.query.path.join("/") : String(req.query.path ?? "")}`;
  const operation = routeOperation(req.method ?? "GET", path);
  if (!operation || !canAccessPolicy(policy.policy, user.groupIds, operation)) {
    await audit({ eventType: "gateway.authorization", outcome: "failure", userId: user.id, detail: { path, reason: "policy_denied", policy_version: policy.version } }).catch(() => undefined);
    finish();
    res.status(403).json({ error: "access_denied" });
    return;
  }
  const env = getEnv();
  const baseUrl = env.LETRON_SSO_ERP_BASE_URL;
  const secret = env.LETRON_SSO_SYNC_SECRET ?? env.AUTH_ERP_SYNC_SECRET;
  if (!baseUrl || !secret) { finish(); res.status(503).json({ error: "gateway_not_configured" }); return; }
  const roles = policyRolesForGroups(policy.policy, user.groupIds);
  const target = new URL(path, `${baseUrl}/`);
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(req.query)) {
    if (key === "path") continue;
    for (const item of Array.isArray(value) ? value : [value]) if (item !== undefined) query.append(key, item);
  }
  target.search = query.toString();
  let response: Response;
  const erpStartedAt = performance.now();
  try {
    response = await fetch(target, {
      method: req.method,
      headers: forwardedHeaders(req, user, policy.version, path, roles, secret),
      body: ["GET", "HEAD"].includes(req.method ?? "GET") ? undefined : new Uint8Array(await body(req)),
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    timings.erp_fetch = duration(erpStartedAt);
    finish();
    res.status(502).json({ error: "erp_gateway_unavailable" });
    return;
  }
  const data = Buffer.from(await response.arrayBuffer());
  timings.erp_fetch = duration(erpStartedAt);
  res.status(response.status);
  response.headers.forEach((value, key) => { if (!['connection', 'content-encoding', 'transfer-encoding', 'server-timing'].includes(key)) res.setHeader(key, value); });
  finish();
  res.send(data);
}
