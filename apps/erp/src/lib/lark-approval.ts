import "server-only";

import { createHash, randomUUID, timingSafeEqual } from "node:crypto";
import { Redis } from "@upstash/redis";
import { ApiRequestError } from "./api-error";
import { frappeGet, frappeList, frappeSubmit, frappeUpdate } from "./frappe-client";
import { supplierPortalConfig } from "./supplier-portal-config";
import { LARK_PO_APPROVAL_DESIGN } from "./lark-approval-design";

// Frappe and Lark payloads are intentionally open-ended at this integration boundary.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;
type ApprovalResponse = { data?: { instance_code?: string } };
type PurchaseApprovalInput = {
  orchestration_id: string; material_request_name: string; request_for_quotation_name: string;
  rfq_number: string; rfq_status: string; supplier_quotation_name: string; quotation_status: string;
  erp_purchase_order_name: string; supplier_response_summary: string; company: string; supplier: string;
  transaction_date: string; schedule_date: string; currency: string; conversion_rate: number;
  total_qty: number; net_total: number; total_taxes: number; grand_total: number; item_summary: string;
  payment_terms: string; delivery_terms: string; justification: string; portal_url: string; items: Row[];
};

let redis: Redis | undefined;
function text(value: unknown): string { return String(value ?? "").trim(); }
function number(value: unknown, fallback = 0): number { const n = Number(value); return Number.isFinite(n) ? n : fallback; }
function config() {
  const approvalCode = process.env.LARK_PO_APPROVAL_CODE?.trim();
  const domain = (process.env.LARK_DOMAIN?.trim() || "https://open.larksuite.com").replace(/\/$/, "");
  const appId = process.env.LARK_APP_ID?.trim(); const appSecret = process.env.LARK_APP_SECRET?.trim();
  if (!approvalCode || !appId || !appSecret) throw new ApiRequestError("configuration_error", "Lark Approval is not configured.", 503);
  return { approvalCode, domain, appId, appSecret };
}
function db(): Redis {
  if (redis) return redis;
  const url = process.env.KV_REST_API_URL?.trim(); const token = process.env.KV_REST_API_TOKEN?.trim();
  if (!url || !token) throw new ApiRequestError("configuration_error", "Lark Approval storage is not configured.", 503);
  redis = new Redis({ url, token }); return redis;
}
async function withLock<T>(key: string, operation: () => Promise<T>): Promise<T> {
  const lockKey = `erp:lark-approval:lock:${createHash("sha256").update(key).digest("hex")}`;
  const owner = randomUUID();
  if (!(await db().set(lockKey, owner, { nx: true, ex: 180 }))) throw new ApiRequestError("lark_approval_in_progress", "Approval is already being processed.", 409, true, 2);
  try { return await operation(); }
  finally {
    await db().eval("if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end", [lockKey], [owner]).catch(() => undefined);
  }
}
async function larkJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const env = config();
  const token = await tenantAccessToken();
  const response = await fetch(new URL(path, env.domain), { ...init, headers: { Accept: "application/json", "Content-Type": "application/json", authorization: `Bearer ${token}`, ...(init.headers ?? {}) }, cache: "no-store", signal: init.signal ?? AbortSignal.timeout(30_000) });
  const payload = await response.json().catch(() => null) as Row | null;
  if (!response.ok || (typeof payload?.code === "number" && payload.code !== 0)) throw new Error(`LARK_REQUEST_FAILED_${response.status || payload?.code || "UNKNOWN"}`);
  return (payload?.data ?? payload) as T;
}
async function tenantAccessToken(): Promise<string> {
  const env = config();
  const cacheKey = "erp:lark-approval:tenant-token";
  const cached = await db().get<{ token: string; expires_at: number }>(cacheKey);
  if (cached && cached.expires_at > Date.now() + 30_000) return cached.token;
  return withLock("tenant-token", async () => {
    const again = await db().get<{ token: string; expires_at: number }>(cacheKey);
    if (again && again.expires_at > Date.now() + 30_000) return again.token;
    const response = await fetch(new URL("/open-apis/auth/v3/tenant_access_token/internal", env.domain), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ app_id: env.appId, app_secret: env.appSecret }), signal: AbortSignal.timeout(10_000) });
    const payload = await response.json().catch(() => null) as Row | null;
    const token = text(payload?.tenant_access_token ?? payload?.data?.tenant_access_token); const expires = number(payload?.expire ?? payload?.data?.expire, 3600);
    if (!response.ok || !token) throw new Error("LARK_TENANT_TOKEN_FAILED");
    await db().set(cacheKey, { token, expires_at: Date.now() + Math.max(60, expires) * 1000 }, { ex: Math.max(60, expires) });
    return token;
  });
}
async function userIdByEmail(email: string): Promise<string> {
  const result = await larkJson<{ user_list?: Array<{ user_id?: string }> }>("/open-apis/contact/v3/users/batch_get_id?user_id_type=user_id", { method: "POST", body: JSON.stringify({ emails: [email] }) });
  const userId = text(result.user_list?.[0]?.user_id); if (!userId) throw new Error("LARK_USER_ID_NOT_FOUND"); return userId;
}
async function sourceInput(input: { orchestrationId: string; supplierQuotationName: string; erpPurchaseOrderName: string; justification?: string }): Promise<PurchaseApprovalInput> {
  const mr = (await frappeList<Row>("Material Request", [["Material Request", "custom_letron_orchestration_id", "=", input.orchestrationId]], ["name"], 10))[0];
  const rfq = (await frappeList<Row>("Request for Quotation", [["Request for Quotation", "custom_letron_orchestration_id", "=", input.orchestrationId]], ["name"], 10))[0];
  if (!mr?.name || !rfq?.name) throw new ApiRequestError("approval_source_missing", "Purchase source documents are missing.", 409);
  const [mrDoc, rfqDoc, sq, po] = await Promise.all([frappeGet<Row>("Material Request", text(mr.name)), frappeGet<Row>("Request for Quotation", text(rfq.name)), frappeGet<Row>("Supplier Quotation", input.supplierQuotationName), frappeGet<Row>("Purchase Order", input.erpPurchaseOrderName)]);
  if (Number(sq.docstatus ?? 0) !== 1 || Number(po.docstatus ?? 0) !== 0) throw new ApiRequestError("approval_source_status_invalid", "Approval source status is invalid.", 409);
  if (text(po.custom_letron_orchestration_id) !== input.orchestrationId || text(sq.custom_letron_orchestration_id) !== input.orchestrationId) throw new ApiRequestError("approval_correlation_mismatch", "Approval source correlation does not match.", 409);
  if (text(po.supplier) !== text(sq.supplier) || text(po.company) !== text(sq.company ?? rfqDoc.company)) throw new ApiRequestError("approval_source_mismatch", "Purchase sources do not match.", 409);
  const sourceItems = Array.isArray(sq.items) ? sq.items as Row[] : []; if (!sourceItems.length) throw new ApiRequestError("approval_items_missing", "Supplier quotation has no items.", 409);
  const purchaseItems = Array.isArray(po.items) ? po.items as Row[] : [];
  const quotationItemNames = new Set(sourceItems.map((item) => text(item.name)).filter(Boolean));
  if (!purchaseItems.length || purchaseItems.some((item) => text(item.supplier_quotation) !== text(sq.name) || !text(item.supplier_quotation_item) || !quotationItemNames.has(text(item.supplier_quotation_item)))) throw new ApiRequestError("approval_po_quotation_mismatch", "Purchase Order items do not belong to the selected Supplier Quotation.", 409);
  const items = sourceItems.map((item) => ({ item_code: text(item.item_code), item_name: text(item.item_name), description: text(item.description), qty: number(item.qty), uom: text(item.uom), rate: number(item.rate), amount: number(item.amount, number(item.qty) * number(item.rate)), warehouse: text(item.warehouse), material_request: text(item.material_request || mrDoc.name), material_request_item: text(item.material_request_item), request_for_quotation: text(item.request_for_quotation || rfqDoc.name), request_for_quotation_item: text(item.request_for_quotation_item), supplier_quotation: text(sq.name), supplier_quotation_item: text(item.name) }));
  if (items.some((item) => !item.item_code || item.qty <= 0 || item.rate < 0)) throw new ApiRequestError("approval_item_invalid", "Supplier quotation item is invalid.", 409);
  return { orchestration_id: input.orchestrationId, material_request_name: text(mrDoc.name), request_for_quotation_name: text(rfqDoc.name), rfq_number: text(rfqDoc.name), rfq_status: text(rfqDoc.status || "Draft"), supplier_quotation_name: text(sq.name), quotation_status: "Submitted", erp_purchase_order_name: text(po.name), supplier_response_summary: `${text(sq.supplier)}: Submitted (${text(sq.name)})`, company: text(po.company), supplier: text(po.supplier), transaction_date: text(po.transaction_date || sq.transaction_date), schedule_date: text(po.schedule_date || sq.schedule_date || po.transaction_date), currency: text(po.currency || sq.currency || "VND"), conversion_rate: number(po.conversion_rate, 1), total_qty: items.reduce((sum, item) => sum + item.qty, 0), net_total: number(sq.net_total, items.reduce((sum, item) => sum + item.amount, 0)), total_taxes: number(sq.total_taxes_and_charges), grand_total: number(sq.grand_total, number(sq.net_total, items.reduce((sum, item) => sum + item.amount, 0)) + number(sq.total_taxes_and_charges)), item_summary: items.map((item, index) => `${index + 1}. ${item.item_code} | qty=${item.qty} | rate=${item.rate}`).join("\n"), payment_terms: text(sq.terms), delivery_terms: text(sq.incoterm || sq.named_place), justification: text(input.justification) || `Chọn báo giá ${sq.name} cho RFQ ${rfqDoc.name}`, portal_url: `${supplierPortalConfig().next_internal_base_url}/supplier`, items };
}
function parseForm(value: unknown): Row[] { if (!value || typeof value !== "object" || Array.isArray(value) || typeof (value as Row).form_content !== "string") throw new Error("LARK_APPROVAL_FORM_INVALID"); const parsed = JSON.parse((value as Row).form_content) as unknown; if (!Array.isArray(parsed)) throw new Error("LARK_APPROVAL_FORM_INVALID"); return parsed as Row[]; }
function approvalForm(definitionForm: unknown, input: PurchaseApprovalInput): Row[] {
  const fields = parseForm(definitionForm); const normalize = (value: unknown) => text(value).replace(/\s+/g, " ").toLowerCase();
  const field = (key: string) => { const design = LARK_PO_APPROVAL_DESIGN.fields.find((item) => item.key === key); const found = fields.find((item) => text(item.id) === design?.sourceId || text(item.custom_id) === design?.sourceId); if (!design || !found || normalize(found.type) !== normalize(design.type)) throw new Error(`LARK_APPROVAL_FIELD_INVALID_${key}`); return found; };
  const reason = field("reason"); const reference = field("reference"); const type = field("purchaseType"); const date = field("deliveryDate"); const details = field("details"); const payment = field("paymentTerms"); const delivery = field("deliveryTerms");
  const children = Array.isArray(details.value) ? details.value as Row[] : []; const child = (key: string) => { const design = LARK_PO_APPROVAL_DESIGN.table.columns.find((item) => item.key === key); const found = children.find((item) => text(item.id) === design?.id || text(item.custom_id) === design?.id); if (!design || !found) throw new Error(`LARK_APPROVAL_COLUMN_INVALID_${key}`); return found; };
  const summary = [`PO: ${input.erp_purchase_order_name}`, `MR: ${input.material_request_name}`, `RFQ: ${input.rfq_number}`, `Quotation: ${input.supplier_quotation_name}`, `Orchestration: ${input.orchestration_id}`].join("\n");
  const rows = input.items.map((item) => [{ id: text(child("itemSummary").id), type: "input", value: `${text(item.item_name) || text(item.item_code)} | ${text(item.description) || "Không có mô tả"}` }, { id: text(child("supplierRfq").id), type: "input", value: `${input.supplier} | RFQ: ${input.rfq_number}` }, { id: text(child("quantity").id), type: "input", value: String(number(item.qty)) }, { id: text(child("unitPrice").id), type: "input", value: `${number(item.rate).toLocaleString("en-US")} ${input.currency}` }, { id: text(child("lineTotal").id), type: "input", value: `${(number(item.qty) * number(item.rate)).toLocaleString("en-US")} ${input.currency}` }]);
  const production = Array.isArray(type.value) ? (type.value as Row[]).find((item) => text(item.value) === "k3qy4q90-ya5zdx7hyh-3") : undefined; if (!production) throw new Error("LARK_APPROVAL_PURCHASE_TYPE_NOT_CONFIGURED");
  return [{ id: text(reason.id), type: text(reason.type), value: input.justification }, { id: text(reference.id), type: text(reference.type), value: summary }, { id: text(type.id), type: text(type.type), value: text(production.value) }, { id: text(date.id), type: text(date.type), value: `${input.schedule_date}T00:00:00+07:00` }, { id: text(payment.id), type: text(payment.type), value: input.payment_terms || "Không có" }, { id: text(delivery.id), type: text(delivery.type), value: input.delivery_terms || "Không có" }, { id: text(details.id), type: text(details.type), value: rows }];
}
async function definition(): Promise<Row> { const env = config(); const result = await larkJson<Row>(`/open-apis/approval/v4/approvals/${encodeURIComponent(env.approvalCode)}`); if (!result || typeof result !== "object") throw new Error("LARK_APPROVAL_DEFINITION_MISSING"); return result; }
export async function openPurchaseApproval(input: { orchestrationId: string; supplierQuotationName: string; erpPurchaseOrderName: string; justification?: string }): Promise<{ instanceCode: string; erpPurchaseOrderName: string; idempotent: boolean }> { return withLock(`open:${input.orchestrationId}`, async () => { const env = config(); const source = await sourceInput(input); const definitionDoc = await definition(); const submitter = await userIdByEmail(supplierPortalConfig().approval_submitter_email); const approverEmail = process.env.LARK_PO_APPROVER_EMAIL?.trim(); const approverId = approverEmail ? await userIdByEmail(approverEmail) : ""; const nodes = Array.isArray(definitionDoc.node_list) ? (definitionDoc.node_list as Row[]).filter((node) => node?.need_approver === true).map((node) => ({ key: text(node.node_id), value: approverId ? [approverId] : [] })) : []; if (nodes.some((node) => !node.value.length)) throw new Error("LARK_PO_APPROVER_NOT_CONFIGURED"); const result = await larkJson<ApprovalResponse["data"]>("/open-apis/approval/v4/instances?user_id_type=user_id", { method: "POST", body: JSON.stringify({ approval_code: env.approvalCode, user_id: submitter, form: JSON.stringify(approvalForm(definitionDoc.form, source)), uuid: createHash("sha256").update(`${source.orchestration_id}:${source.erp_purchase_order_name}`).digest("hex").toString(), title: `Phê duyệt yêu cầu mua hàng - ${source.erp_purchase_order_name}`, ...(nodes.length ? { node_approver_user_id_list: nodes } : {}) }) }); const instanceCode = text(result?.instance_code); if (!instanceCode) throw new Error("LARK_APPROVAL_INSTANCE_CREATE_FAILED"); await frappeUpdate("Purchase Order", source.erp_purchase_order_name, { custom_lark_approval_instance_code: instanceCode, custom_lark_approval_status: "Pending Approval", custom_lark_error: "" }); return { instanceCode, erpPurchaseOrderName: source.erp_purchase_order_name, idempotent: false }; }); }
export async function readPurchaseApproval(instanceCode: string): Promise<Row> { const result = await larkJson<Row>(`/open-apis/approval/v4/instances/${encodeURIComponent(instanceCode)}?user_id_type=user_id`); if (!result || typeof result !== "object") throw new Error("LARK_APPROVAL_INSTANCE_MISSING"); return result; }
export async function submitApprovedPurchaseOrder(instanceCode: string, poName: string): Promise<{ name: string; idempotent: boolean }> { return withLock(`submit:${poName}`, async () => { const po = await frappeGet<Row>("Purchase Order", poName); if (text(po.custom_lark_approval_instance_code) !== instanceCode) throw new Error("ERP_PO_APPROVAL_MAPPING_MISMATCH"); if (Number(po.docstatus ?? 0) === 1) return { name: poName, idempotent: true }; if (Number(po.docstatus ?? 0) !== 0 || !text(po.custom_letron_orchestration_id)) throw new Error("ERP_PO_NOT_SUBMITTABLE"); await frappeUpdate("Purchase Order", poName, { custom_lark_approval_status: "Approved", custom_lark_error: "" }); await frappeSubmit({ doctype: "Purchase Order", name: poName }); return { name: poName, idempotent: false }; }); }
export async function markPurchaseApprovalState(poName: string, status: "Rejected" | "Canceled" | "ERP Failed", error = ""): Promise<void> { await frappeUpdate("Purchase Order", poName, { custom_lark_approval_status: status, custom_lark_error: error }); }
async function mappedPurchaseOrder(instanceCode: string): Promise<string> { const rows = await frappeList<Row>("Purchase Order", [["Purchase Order", "custom_lark_approval_instance_code", "=", instanceCode]], ["name", "docstatus", "custom_letron_orchestration_id"], 5); if (rows.length !== 1 || !text(rows[0]?.name)) throw new Error("ERP_PO_APPROVAL_MAPPING_MISSING"); return text(rows[0].name); }
export async function reconcilePurchaseApproval(instanceCode: string): Promise<{ status: string; erpPurchaseOrderName: string }> { const instance = await readPurchaseApproval(instanceCode); const status = text(instance.status).toUpperCase(); const poName = await mappedPurchaseOrder(instanceCode); if (["REJECTED", "CANCELED", "CANCELLED"].includes(status)) { await markPurchaseApprovalState(poName, status === "REJECTED" ? "Rejected" : "Canceled"); return { status, erpPurchaseOrderName: poName }; } if (status !== "APPROVED") return { status, erpPurchaseOrderName: poName }; await submitApprovedPurchaseOrder(instanceCode, poName); return { status: "ERP_SUBMITTED", erpPurchaseOrderName: poName }; }
export async function approvePurchaseApproval(instanceCode: string): Promise<{ status: string; taskId?: string; idempotent: boolean }> { const instance = await readPurchaseApproval(instanceCode); const status = text(instance.status).toUpperCase(); if (status === "APPROVED") return { status, idempotent: true }; if (["REJECTED", "CANCELED", "CANCELLED"].includes(status)) throw new Error(`LARK_APPROVAL_ALREADY_${status}`); const email = process.env.LARK_PO_APPROVER_EMAIL?.trim(); if (!email) throw new Error("LARK_PO_APPROVER_NOT_CONFIGURED"); const userId = await userIdByEmail(email); const task = (Array.isArray(instance.task_list) ? instance.task_list as Row[] : []).find((item) => text(item.status).toUpperCase() === "PENDING" && text(item.user_id) === userId); const taskId = text(task?.id); if (!taskId) throw new Error("LARK_APPROVAL_PENDING_TASK_NOT_FOUND"); const env = config(); await larkJson(`/open-apis/approval/v4/tasks/approve?user_id_type=user_id`, { method: "POST", body: JSON.stringify({ approval_code: env.approvalCode, instance_code: instanceCode, user_id: userId, task_id: taskId, comment: "real-test auto-approved" }) }); return { status: "APPROVED_REQUESTED", taskId, idempotent: false }; }
export function validApprovalWebhookSignature(body: string, timestamp: string, nonce: string, supplied: string): boolean { const key = process.env.LARK_EVENT_ENCRYPT_KEY?.trim(); if (!key || !timestamp || !nonce || !supplied || !/^\d+$/.test(timestamp) || Math.abs(Math.floor(Date.now() / 1000) - Number(timestamp)) > 300) return false; const expected = createHash("sha256").update(`${timestamp}${nonce}${key}${body}`).digest("hex"); const left = Buffer.from(supplied, "utf8"); const right = Buffer.from(expected, "utf8"); return left.length === right.length && timingSafeEqual(left, right); }
export async function claimApprovalWebhook(eventId: string): Promise<"claimed" | "processing" | "completed"> { const key = `erp:lark-approval:event:${eventId}`; const claimed = await db().set(key, "processing", { nx: true, ex: 120 }); if (claimed) return "claimed"; const state = await db().get<string>(key); return state === "completed" ? "completed" : "processing"; }
export async function completeApprovalWebhook(eventId: string): Promise<void> { await db().set(`erp:lark-approval:event:${eventId}`, "completed", { ex: 7 * 86400 }); }
export async function releaseApprovalWebhook(eventId: string): Promise<void> { await db().del(`erp:lark-approval:event:${eventId}`); }
