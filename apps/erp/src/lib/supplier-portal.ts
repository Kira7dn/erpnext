import "server-only";

import { createHmac, randomUUID } from "node:crypto";
import { ApiRequestError, type RemoteErrorPayload } from "./api-error";
import { publicErrorMessage, retryAfterSeconds, validErrorCode } from "./error-contract";
import { supplierPortalConfig } from "@/lib/supplier-portal-config";

type SupplierPortalResponse<T> = {
  message?: T;
  data?: T;
} & RemoteErrorPayload;

export type SupplierPortalMail = {
  to: string;
  subject: string;
  body_html: string;
  body_plain_text: string;
  idempotency_key: string;
};

function supplierPortalError(
  status: number,
  payload: RemoteErrorPayload,
  prefix = "supplier_portal",
): ApiRequestError {
  let code = `${prefix}_request_rejected`;
  if (status === 401) code = `${prefix}_authentication_required`;
  else if (status === 403) code = `${prefix}_access_denied`;
  else if (status === 404) code = `${prefix}_not_found`;
  else if (status === 429) code = `${prefix}_rate_limited`;
  else if (status >= 500) code = `${prefix}_unavailable`;
  const upstreamCode = validErrorCode(payload.error);
  if (upstreamCode?.startsWith("supplier_")) code = upstreamCode;
  const retryAfter = retryAfterSeconds(payload.retry_after_seconds);
  return new ApiRequestError(
    code,
    publicErrorMessage(code, status),
    status,
    status === 429 || status >= 500,
    retryAfter,
  );
}

function supplierPortalUnavailable(message: string): ApiRequestError {
  return new ApiRequestError("supplier_portal_unavailable", message, 503, true);
}

function supplierPortalSecret(): string {
  return (process.env.LETRON_SSO_SYNC_SECRET ?? "").trim();
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
  const signature = controlSign(path, requestId, now, expires);
  let response: Response;
  try {
    response = await fetch(`${erpBaseUrl()}${path}`, {
      method: "POST",
      headers: {
        Accept: "application/json", "Content-Type": "application/json",
        "X-Letron-Control-Timestamp": String(now), "X-Letron-Control-Expires-At": String(expires),
        "X-Letron-Control-Request-Id": requestId, "X-Letron-Control-Signature": signature,
      }, body: JSON.stringify(body), cache: "no-store", signal: AbortSignal.timeout(30_000),
    });
  } catch {
    throw supplierPortalUnavailable("Supplier portal control service is unavailable.");
  }
  const payload = (await response.json().catch(() => ({}))) as SupplierPortalResponse<T>;
  if (!response.ok) throw supplierPortalError(response.status, payload);
  return payload.message as T;
}

export async function supplierPortalRequest<T>(
  methodName: string,
  body: Record<string, unknown>,
): Promise<T> {
  const path = `/api/method/letron_api.supplier_portal.${methodName}`;
  const now = Math.floor(Date.now() / 1000);
  const expires = now + 60;
  const requestId = randomUUID();
  const signature = sign(path, requestId, now, expires);
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
        "X-Letron-Supplier-Signature": signature,
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
  if (raw) payload = JSON.parse(raw) as SupplierPortalResponse<T>;
  if (!response.ok) throw supplierPortalError(response.status, payload);
  return payload.message as T;
}

export async function sendSupplierPortalMail(input: SupplierPortalMail): Promise<{ messageId: string; idempotent?: boolean }> {
  const authBase = supplierPortalConfig().auth_base_url.replace(/\/$/, "");
  const apiKey = process.env.LETRON_API_KEY?.trim();
  if (!authBase || !apiKey) throw new ApiRequestError("configuration_error", "Supplier mail service is not configured.", 503);
  let response: Response;
  try {
    response = await fetch(`${authBase}/api/internal/lark-mail/send`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json", Authorization: `Bearer ${apiKey}`, "X-Idempotency-Key": input.idempotency_key },
      body: JSON.stringify(input),
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    throw new ApiRequestError("lark_mail_unavailable", "Supplier mail service is unavailable.", 503, true);
  }
  const payload = await response.json().catch(() => ({})) as RemoteErrorPayload & { data?: { messageId?: string; idempotent?: boolean } };
  if (!response.ok) {
    const retryAfter = retryAfterSeconds(payload.retry_after_seconds) ?? retryAfterSeconds(response.headers.get("Retry-After"));
    const code = validErrorCode(payload.error) ?? "lark_mail_send_failed";
    throw new ApiRequestError(code, publicErrorMessage(code, response.status), response.status, response.status === 409 || response.status >= 500, retryAfter);
  }
  const result = payload.data;
  if (!result || !result.messageId) throw new ApiRequestError("lark_mail_send_failed", "Supplier mail delivery returned no message ID.", 502, true);
  return { messageId: result.messageId, idempotent: result.idempotent };
}

export async function supplierPortalUpload<T>(
  methodName: string,
  form: FormData,
): Promise<T> {
  const path = `/api/method/letron_api.supplier_portal.${methodName}`;
  const now = Math.floor(Date.now() / 1000);
  const expires = now + 60;
  const requestId = randomUUID();
  const signature = sign(path, requestId, now, expires);
  let response: Response;
  try {
    response = await fetch(`${erpBaseUrl()}${path}`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "X-Letron-Supplier-Timestamp": String(now),
        "X-Letron-Supplier-Expires-At": String(expires),
        "X-Letron-Supplier-Request-Id": requestId,
        "X-Letron-Supplier-Signature": signature,
      },
      body: form,
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    throw supplierPortalUnavailable("Supplier portal upload service is unavailable.");
  }
  const payload = (await response.json().catch(() => ({}))) as SupplierPortalResponse<T>;
  if (!response.ok) throw supplierPortalError(response.status, payload);
  return payload.message as T;
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
    throw supplierPortalError(response.status, payload, "supplier_approval");
  return payload.data as T;
}
