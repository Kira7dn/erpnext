import "server-only";

import { createHmac, randomUUID } from "node:crypto";
import { ApiRequestError, remoteErrorMessage, type RemoteErrorPayload } from "./api-error";
import { supplierPortalConfig } from "@/lib/supplier-portal-config";

type SupplierPortalResponse<T> = {
  message?: T;
  data?: T;
} & RemoteErrorPayload;

function supplierPortalError(
  status: number,
  payload: RemoteErrorPayload,
  fallback: string,
  prefix = "supplier_portal",
): ApiRequestError {
  let code = `${prefix}_request_rejected`;
  if (status === 401) code = `${prefix}_authentication_required`;
  else if (status === 403) code = `${prefix}_access_denied`;
  else if (status === 404) code = `${prefix}_not_found`;
  else if (status === 429) code = `${prefix}_rate_limited`;
  else if (status >= 500) code = `${prefix}_unavailable`;
  return new ApiRequestError(
    code,
    remoteErrorMessage(payload, fallback),
    status,
    status === 429 || status >= 500,
  );
}

function supplierPortalUnavailable(message: string): ApiRequestError {
  return new ApiRequestError("supplier_portal_unavailable", message, 503, true);
}

function supplierPortalSecret(): string {
  return (process.env.LETRON_SUPPLIER_PORTAL_SECRET ?? process.env.LETRON_SSO_SYNC_SECRET ?? "").trim();
}

function erpBaseUrl(): string {
  const value = supplierPortalConfig().erp_base_url.trim();
  if (!value) throw new ApiRequestError("configuration_error", "Supplier portal service is not configured.", 503);
  return value.replace(/\/$/, "");
}

function sign(path: string, requestId: string, now: number, expires: number): string {
  const secret = supplierPortalSecret();
  if (!secret) throw new ApiRequestError("configuration_error", "Supplier portal service is not configured.", 503);
  return createHmac("sha256", secret)
    .update(`${now}.${expires}.POST.${path}.${requestId}`)
    .digest("hex");
}

function controlSign(path: string, requestId: string, now: number, expires: number): string {
  const secret = process.env.LETRON_SSO_SYNC_SECRET?.trim();
  if (!secret) throw new ApiRequestError("configuration_error", "Supplier portal control service is not configured.", 503);
  return createHmac("sha256", secret).update(`${now}.${expires}.POST.${path}.${requestId}`).digest("hex");
}

export async function supplierPortalControlRequest<T>(methodName: string, body: Record<string, unknown>): Promise<T> {
  const path = `/api/method/letron_api.supplier_portal.${methodName}`;
  const now = Math.floor(Date.now() / 1000);
  const expires = now + 60;
  const requestId = randomUUID();
  let response: Response;
  try {
    response = await fetch(`${erpBaseUrl()}${path}`, {
      method: "POST",
      headers: {
        Accept: "application/json", "Content-Type": "application/json",
        "X-Letron-Control-Timestamp": String(now), "X-Letron-Control-Expires-At": String(expires),
        "X-Letron-Control-Request-Id": requestId, "X-Letron-Control-Signature": controlSign(path, requestId, now, expires),
      }, body: JSON.stringify(body), cache: "no-store", signal: AbortSignal.timeout(30_000),
    });
  } catch {
    throw supplierPortalUnavailable("Supplier portal control service is unavailable.");
  }
  const payload = (await response.json().catch(() => ({}))) as SupplierPortalResponse<T>;
  if (!response.ok) throw supplierPortalError(response.status, payload, "Supplier portal control request failed.");
  return (payload.data ?? payload.message) as T;
}

export async function supplierPortalRequest<T>(
  methodName: string,
  body: Record<string, unknown>,
): Promise<T> {
  const path = `/api/method/letron_api.supplier_portal.${methodName}`;
  const now = Math.floor(Date.now() / 1000);
  const expires = now + 60;
  const requestId = randomUUID();
  let response: Response;
  try {
    response = await fetch(`${erpBaseUrl()}${path}`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-Letron-Supplier-Timestamp": String(now),
        "X-Letron-Supplier-Expires-At": String(expires),
        "X-Letron-Supplier-Request-Id": requestId,
        "X-Letron-Supplier-Signature": sign(path, requestId, now, expires),
      },
      body: JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    throw supplierPortalUnavailable("Supplier portal service is unavailable.");
  }
  const raw = await response.text();
  let payload = {} as SupplierPortalResponse<T>;
  try { payload = raw ? JSON.parse(raw) as SupplierPortalResponse<T> : payload; } catch { /* Keep the HTTP fallback below. */ }
  if (!response.ok) throw supplierPortalError(response.status, payload, "Supplier portal request failed.");
  return (payload.data ?? payload.message) as T;
}

export async function supplierPortalUpload<T>(
  methodName: string,
  form: FormData,
): Promise<T> {
  const path = `/api/method/letron_api.supplier_portal.${methodName}`;
  const now = Math.floor(Date.now() / 1000);
  const expires = now + 60;
  const requestId = randomUUID();
  let response: Response;
  try {
    response = await fetch(`${erpBaseUrl()}${path}`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "X-Letron-Supplier-Timestamp": String(now),
        "X-Letron-Supplier-Expires-At": String(expires),
        "X-Letron-Supplier-Request-Id": requestId,
        "X-Letron-Supplier-Signature": sign(path, requestId, now, expires),
      },
      body: form,
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    throw supplierPortalUnavailable("Supplier portal upload service is unavailable.");
  }
  const payload = (await response.json().catch(() => ({}))) as SupplierPortalResponse<T>;
  if (!response.ok) throw supplierPortalError(response.status, payload, "Supplier portal upload failed.");
  return (payload.data ?? payload.message) as T;
}

export async function supplierPortalCronRequest<T>(): Promise<T> {
  const secret = process.env.LETRON_SUPPLIER_PORTAL_CRON_SECRET?.trim();
  if (!secret) throw new ApiRequestError("configuration_error", "Supplier portal scheduler is not configured.", 503);
  return supplierPortalRequest<T>("evaluate_due_processes", { cron_secret: secret });
}

export async function openSupplierApproval<T>(input: {
  orchestration_id: string;
  selected_supplier_quotation_name: string;
  justification: string;
}): Promise<T> {
  const secret = supplierPortalSecret();
  const authBase = supplierPortalConfig().auth_base_url.replace(/\/$/, "");
  if (!secret || !authBase)
    throw new ApiRequestError("configuration_error", "Supplier approval service is not configured.", 503);
  const response = await fetch(`${authBase}/api/integrations/lark/supplier-portal/open-approval`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json", Authorization: `Bearer ${secret}` },
    body: JSON.stringify(input),
    cache: "no-store",
    signal: AbortSignal.timeout(60_000),
  });
  const payload = await response.json().catch(() => ({})) as RemoteErrorPayload & { data?: T };
  if (!response.ok)
    throw supplierPortalError(response.status, payload, "Supplier approval service rejected the request.", "supplier_approval");
  return (payload.data ?? payload) as T;
}
