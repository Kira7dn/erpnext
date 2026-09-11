import "server-only";

import { ApiRequestError, type RemoteErrorPayload } from "./api-error";
import { publicErrorMessage, retryAfterSeconds, validErrorCode } from "./error-contract";
import { supplierPortalConfig } from "./supplier-portal-config";
import { openPurchaseApproval } from "./lark-approval";
import { approvalState, evaluateApprovalGate, evaluateDueOrchestrations, getSubmissions, processSummary, registerWarehouseReceipt, revokeAccess, submitQuotation, uploadInvoice } from "./supplier-portal-core";
import { buildInvoiceRequestMail, decryptSupplierPortalToken } from "./supplier-portal-session";

export type SupplierPortalMail = { to: string; subject: string; body_html: string; body_plain_text: string; idempotency_key: string };
function local(body: Record<string, unknown>): string { return String(body.portal_access_id ?? body.access_id ?? ""); }
export async function supplierPortalRequest<T>(method: string, body: Record<string, unknown>): Promise<T> {
  switch (method) {
    case "get_process_summary": return await processSummary(local(body)) as T;
    case "submit_quotation": return await submitQuotation(local(body), body) as T;
    case "evaluate_approval_gate": return await evaluateApprovalGate(String(body.orchestration_id ?? body.material_request ?? "")) as T;
    case "get_submissions": return await getSubmissions(local(body)) as T;
    case "get_purchase_order": return (await processSummary(local(body))).purchase_order as T;
    case "get_payment_status": { const summary = await processSummary(local(body)); return { purchase_invoice: summary.purchase_invoice, payment_status: summary.payment_status } as T; }
    case "claim_approval_opening": return await approvalState(String(body.process), "claim") as T;
    case "release_approval_opening": return await approvalState(String(body.process), "release") as T;
    case "mark_approval_opened": return await approvalState(String(body.process), "opened", String(body.approval_id)) as T;
    case "revoke_access": return await revokeAccess(String(body.access_id ?? body.portal_access_id)) as T;
    default: throw new ApiRequestError("not_found", `Unsupported Supplier Portal operation: ${method}.`, 404);
  }
}
export async function supplierPortalControlRequest<T>(method: string, body: Record<string, unknown>): Promise<T> {
  if (method === "revoke_access") return await revokeAccess(String(body.access_id ?? body.portal_access_id)) as T;
  throw new ApiRequestError("not_found", `Unsupported Supplier Portal control operation: ${method}.`, 404);
}
export async function supplierPortalUpload<T>(method: string, form: FormData): Promise<T> {
  if (method !== "upload_xml_invoice") throw new ApiRequestError("not_found", `Unsupported Supplier Portal upload operation: ${method}.`, 404);
  return await uploadInvoice(String(form.get("portal_access_id")), form) as T;
}
export async function supplierPortalCronRequest<T>(): Promise<T> { return await evaluateDueOrchestrations() as T; }

export async function sendSupplierPortalMail(input: SupplierPortalMail): Promise<{ messageId: string; idempotent?: boolean }> {
  const authBase = supplierPortalConfig().auth_base_url.replace(/\/$/, ""); const apiKey = process.env.LETRON_INTERNAL_API_SECRET?.trim();
  if (!authBase || !apiKey) throw new ApiRequestError("configuration_error", "Supplier mail service is not configured.", 503);
  let response: Response;
  try { response = await fetch(`${authBase}/api/internal/lark-mail/send`, { method: "POST", headers: { Accept: "application/json", "Content-Type": "application/json", Authorization: `Bearer ${apiKey}`, "X-Idempotency-Key": input.idempotency_key }, body: JSON.stringify(input), cache: "no-store", signal: AbortSignal.timeout(30_000) }); }
  catch { throw new ApiRequestError("lark_mail_unavailable", "Supplier mail service is unavailable.", 503, true); }
  const payload = await response.json().catch(() => ({})) as RemoteErrorPayload & { data?: { messageId?: string; idempotent?: boolean } };
  if (!response.ok) { const retry = retryAfterSeconds(payload.retry_after_seconds) ?? retryAfterSeconds(response.headers.get("Retry-After")); const code = validErrorCode(payload.error) ?? "lark_mail_send_failed"; throw new ApiRequestError(code, publicErrorMessage(code, response.status), response.status, response.status === 409 || response.status >= 500, retry); }
  if (!payload.data?.messageId) throw new ApiRequestError("lark_mail_send_failed", "Supplier mail delivery returned no message ID.", 502, true);
  return payload.data as { messageId: string; idempotent?: boolean };
}
export async function notifySupplierInvoiceRequest(receiptName: string): Promise<{ messageId: string; idempotent?: boolean }> {
  const { access } = await registerWarehouseReceipt(receiptName);
  return sendSupplierPortalMail(buildInvoiceRequestMail(access, decryptSupplierPortalToken(access), receiptName));
}
export async function openSupplierApproval<T>(input: { orchestration_id: string; selected_supplier_quotation_name: string; erp_purchase_order_name: string; material_request_name?: string; request_for_quotation_name?: string; justification: string }): Promise<T> {
  return await openPurchaseApproval({ orchestrationId: input.orchestration_id, supplierQuotationName: input.selected_supplier_quotation_name, erpPurchaseOrderName: input.erp_purchase_order_name, materialRequestName: input.material_request_name, rfqName: input.request_for_quotation_name, justification: input.justification }) as T;
}
