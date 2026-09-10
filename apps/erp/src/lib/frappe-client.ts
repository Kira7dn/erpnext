import "server-only";

import { createHmac, randomUUID } from "node:crypto";
import { ApiRequestError } from "./api-error";
import { supplierPortalConfig } from "./supplier-portal-config";

type FrappeEnvelope<T> = { data?: T; exc?: unknown; _server_messages?: unknown };

function baseUrl(): string { return supplierPortalConfig().erp_base_url.replace(/\/$/, ""); }

function headers(extra?: HeadersInit): Headers {
  const result = new Headers(extra);
  result.set("Accept", "application/json");
  const secret = process.env.LETRON_SSO_SYNC_SECRET?.trim();
  if (!secret) throw new ApiRequestError("configuration_error", "ERP system automation is not configured.", 503);
  const timestamp = Math.floor(Date.now() / 1000);
  const expires = timestamp + 60;
  const path = (result.get("X-Letron-Request-Path") ?? "").split("?", 1)[0];
  const method = result.get("X-Letron-Request-Method") ?? "GET";
  const requestId = randomUUID();
  const payload = `${timestamp}.${expires}.${method}.${path}.${requestId}`;
  result.set("X-Letron-Control-Timestamp", String(timestamp));
  result.set("X-Letron-Control-Expires-At", String(expires));
  result.set("X-Letron-Control-Request-Id", requestId);
  result.set("X-Letron-Control-Signature", createHmac("sha256", secret).update(payload).digest("hex"));
  result.delete("X-Letron-Request-Path");
  result.delete("X-Letron-Request-Method");
  return result;
}

function encodeDocType(value: string): string { return encodeURIComponent(value); }
function query(value: unknown): string { return encodeURIComponent(JSON.stringify(value)); }

export async function frappeRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    const requestHeaders = new Headers(init.headers);
    requestHeaders.set("X-Letron-Request-Path", path);
    requestHeaders.set("X-Letron-Request-Method", init.method ?? "GET");
    response = await fetch(`${baseUrl()}${path}`, { ...init, headers: headers(requestHeaders), cache: "no-store", signal: init.signal ?? AbortSignal.timeout(30_000) });
  } catch {
    throw new ApiRequestError("supplier_portal_unavailable", "ERP service is unavailable.", 503, true);
  }
  const raw = await response.text();
  let payload: FrappeEnvelope<T> = {};
  try { payload = raw ? JSON.parse(raw) as FrappeEnvelope<T> : {}; } catch { throw new ApiRequestError("supplier_portal_unavailable", "ERP returned an invalid response.", 502, true); }
  if (!response.ok) throw new ApiRequestError(response.status === 404 ? "supplier_portal_not_found" : "supplier_portal_request_rejected", `ERP request failed (${response.status}).`, response.status, response.status >= 500);
  if (payload.data === undefined) throw new ApiRequestError("supplier_portal_request_rejected", "ERP returned no data envelope.", 502, true);
  return payload.data;
}

export async function frappeGet<T>(doctype: string, name: string): Promise<T> {
  return frappeRequest<T>(`/api/resource/${encodeDocType(doctype)}/${encodeURIComponent(name)}`);
}

export async function frappeList<T>(doctype: string, filters: unknown[] = [], fields: string[] = ["name"], limit = 100): Promise<T[]> {
  const params = new URLSearchParams({ filters: query(filters), fields: query(fields), limit_page_length: String(limit) });
  const rows = await frappeRequest<T[]>(`/api/resource/${encodeDocType(doctype)}?${params}`);
  return Array.isArray(rows) ? rows : [];
}

export async function frappeInsert<T>(doc: Record<string, unknown>): Promise<T> {
  return frappeRequest<T>(`/api/resource/${encodeDocType(String(doc.doctype ?? ""))}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(doc) });
}

export async function frappeUpdate<T>(doctype: string, name: string, fields: Record<string, unknown>): Promise<T> {
  return frappeRequest<T>(`/api/resource/${encodeDocType(doctype)}/${encodeURIComponent(name)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(fields) });
}

export async function frappeSubmit<T>(doc: Record<string, unknown>): Promise<T> {
  return frappeRequest<T>("/api/method/frappe.client.submit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ doc: JSON.stringify(doc) }) });
}

export async function frappeUpload(file: File, fields: Record<string, string>): Promise<Record<string, unknown>> {
  const form = new FormData();
  form.set("file", file);
  form.set("is_private", "1");
  for (const [key, value] of Object.entries(fields)) form.set(key, value);
  return frappeRequest<Record<string, unknown>>("/api/method/upload_file", { method: "POST", body: form });
}
