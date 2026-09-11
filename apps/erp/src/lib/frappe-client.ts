import "server-only";

import { createHmac, randomUUID } from "node:crypto";
import { ApiRequestError } from "./api-error";
import { supplierPortalConfig } from "./supplier-portal-config";

type FrappeEnvelope<T> = {
  data?: T;
  message?: T;
  exc?: unknown;
  exception?: unknown;
  exc_type?: unknown;
  _server_messages?: unknown;
};

export type ErpPurchaseOrderDraft = {
  name: string;
  docstatus: 0;
  supplier: string;
  company: string;
  transaction_date: string;
  schedule_date: string;
  currency: string;
  conversion_rate: number;
  items: Array<Record<string, unknown>>;
  [key: string]: unknown;
};

export type ErpSupplierQuotationDraft = {
  name: string;
  docstatus: 0;
  supplier: string;
  company: string;
  transaction_date: string;
  currency?: string;
  conversion_rate?: number;
  items: Array<Record<string, unknown>>;
  [key: string]: unknown;
};

function baseUrl(): string { return supplierPortalConfig().erp_base_url.replace(/\/$/, ""); }

function headers(extra?: HeadersInit): Headers {
  const result = new Headers(extra);
  result.set("Accept", "application/json");
  const secret = process.env.LETRON_INTERNAL_API_SECRET?.trim();
  if (!secret) throw new ApiRequestError("configuration_error", "ERP system automation is not configured.", 503);
  const timestamp = Math.floor(Date.now() / 1000);
  const expires = timestamp + 60;
  const rawPath = (result.get("X-Letron-Request-Path") ?? "").split("?", 1)[0];
  const path = decodeURIComponent(rawPath);
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

function upstreamError(payload: FrappeEnvelope<unknown>): string {
  const exception = typeof payload.exception === "string" ? payload.exception.trim() : "";
  const type = typeof payload.exc_type === "string" ? payload.exc_type.trim() : "";
  if (exception && type && exception !== type) return `${type}: ${exception}`;
  if (exception || type) return exception || type;
  if (typeof payload.exc === "string" && payload.exc.trim()) return payload.exc.trim();
  if (typeof payload._server_messages === "string" && payload._server_messages.trim()) return payload._server_messages.trim();
  return "upstream validation failed";
}

export async function frappeRequest<T>(path: string, init: RequestInit = {}, envelope: "data" | "message" = "data"): Promise<T> {
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
  if (!response.ok) {
    const code = response.status === 404 ? "supplier_portal_not_found" : "supplier_portal_request_rejected";
    throw new ApiRequestError(code, `ERP request failed (${response.status}): ${upstreamError(payload)}`, response.status, response.status >= 500);
  }
  const value = payload[envelope];
  if (value === undefined) throw new ApiRequestError("supplier_portal_request_rejected", `ERP returned no ${envelope} envelope.`, 502, true);
  return value;
}

export async function frappeGet<T>(doctype: string, name: string): Promise<T> {
  return frappeRequest<T>(`/api/resource/${encodeDocType(doctype)}/${encodeURIComponent(name)}`);
}

export async function frappeList<T>(doctype: string, filters: unknown[] = [], fields: string[] = ["name"], limit = 100): Promise<T[]> {
  const params = new URLSearchParams({ filters: query(filters), fields: query(fields), limit_page_length: String(limit) });
  const rows = await frappeRequest<T[]>(`/api/resource/${encodeDocType(doctype)}?${params}`);
  return Array.isArray(rows) ? rows : [];
}

export async function frappeInsert<T>(doc: Record<string, unknown>, idempotencyKey?: string): Promise<T> {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (idempotencyKey?.trim()) headers.set("X-Idempotency-Key", idempotencyKey.trim());
  return frappeRequest<T>(`/api/resource/${encodeDocType(String(doc.doctype ?? ""))}`, { method: "POST", headers, body: JSON.stringify(doc) });
}

export async function frappeCreateSupplierQuotation(
  doc: Record<string, unknown>,
  idempotencyKey?: string,
): Promise<ErpSupplierQuotationDraft> {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (idempotencyKey?.trim()) headers.set("X-Idempotency-Key", idempotencyKey.trim());
  return frappeRequest<ErpSupplierQuotationDraft>(
    "/api/v1/crm/supplier-quotations",
    { method: "POST", headers, body: JSON.stringify(doc) },
  );
}

export async function frappeUpdate<T>(doctype: string, name: string, fields: Record<string, unknown>): Promise<T> {
  return frappeRequest<T>(`/api/resource/${encodeDocType(doctype)}/${encodeURIComponent(name)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(fields) });
}

export async function frappeDocumentAction<T>(doctype: string, name: string, action: "submit" | "cancel"): Promise<T> {
  const moduleAndResource: Record<string, string> = {
    "Purchase Invoice": "accounts/purchase-invoices",
    "Purchase Order": "buying/purchase-orders",
    "Purchase Receipt": "stock/purchase-receipts",
    "Supplier Quotation": "crm/supplier-quotations",
  };
  const resource = moduleAndResource[doctype];
  if (!resource) throw new ApiRequestError("configuration_error", `Unsupported ERP document action: ${doctype}.`, 500);
  return frappeRequest<T>(`/api/v1/${resource}/${encodeURIComponent(name)}/${action}`, { method: "POST" }, "message");
}

export async function frappeMakePurchaseOrder(supplierQuotationName: string): Promise<ErpPurchaseOrderDraft> {
  return frappeRequest<ErpPurchaseOrderDraft>(`/api/v1/crm/supplier-quotations/${encodeURIComponent(supplierQuotationName)}/make-purchase-order`, { method: "POST" }, "message");
}

export async function frappeUpload(file: File, fields: Record<string, string>): Promise<Record<string, unknown>> {
  const form = new FormData();
  form.set("file", file);
  form.set("is_private", "1");
  for (const [key, value] of Object.entries(fields)) form.set(key, value);
  return frappeRequest<Record<string, unknown>>("/api/method/upload_file", { method: "POST", body: form }, "message");
}
