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
  disableCaching(res);
  let user = await getUserBySessionToken(tokenFromRequest(req));
  if (!user) { res.status(401).json({ error: "authentication_required" }); return; }
  if (getEnv().LARK_GROUP_SYNC_ENABLED) {
    try {
      await syncLarkGroupsIfStale(user.id);
      user = await getUserBySessionToken(tokenFromRequest(req));
    } catch {
      res.status(503).json({ error: "access_policy_unavailable" });
      return;
    }
    if (!user) { res.status(401).json({ error: "authentication_required" }); return; }
  }
  const policy = await getPublishedPolicy();
  if (!policy) { res.status(503).json({ error: "access_policy_not_published" }); return; }
  const path = `/${Array.isArray(req.query.path) ? req.query.path.join("/") : String(req.query.path ?? "")}`;
  const operation = routeOperation(req.method ?? "GET", path);
  if (!operation || !canAccessPolicy(policy.policy, user.groupIds, operation)) {
    await audit({ eventType: "gateway.authorization", outcome: "failure", userId: user.id, detail: { path, reason: "policy_denied", policy_version: policy.version } }).catch(() => undefined);
    res.status(403).json({ error: "access_denied" });
    return;
  }
  const env = getEnv();
  const baseUrl = env.LETRON_SSO_ERP_BASE_URL;
  const secret = env.LETRON_SSO_SYNC_SECRET ?? env.AUTH_ERP_SYNC_SECRET;
  if (!baseUrl || !secret) { res.status(503).json({ error: "gateway_not_configured" }); return; }
  const roles = policyRolesForGroups(policy.policy, user.groupIds);
  const target = new URL(path, `${baseUrl}/`);
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(req.query)) {
    if (key === "path") continue;
    for (const item of Array.isArray(value) ? value : [value]) if (item !== undefined) query.append(key, item);
  }
  target.search = query.toString();
  let response: Response;
  try {
    response = await fetch(target, {
      method: req.method,
      headers: forwardedHeaders(req, user, policy.version, path, roles, secret),
      body: ["GET", "HEAD"].includes(req.method ?? "GET") ? undefined : new Uint8Array(await body(req)),
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    res.status(502).json({ error: "erp_gateway_unavailable" });
    return;
  }
  res.status(response.status);
  response.headers.forEach((value, key) => { if (!['connection', 'content-encoding', 'transfer-encoding'].includes(key)) res.setHeader(key, value); });
  const data = Buffer.from(await response.arrayBuffer());
  res.send(data);
}
