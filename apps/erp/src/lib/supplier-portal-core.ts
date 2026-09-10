import "server-only";

import { createHash, randomUUID } from "node:crypto";
import { Redis } from "@upstash/redis";
import { ApiRequestError } from "./api-error";
import { frappeGet, frappeInsert, frappeList, frappeSubmit, frappeUpload } from "./frappe-client";
import {
  getAccessById,
  getAccessesForOrchestration,
  registerAccessForOrchestration,
  decryptSupplierPortalToken,
  updateAccess,
  type SupplierPortalAccess,
} from "./supplier-portal-session";

// Frappe's native REST payload is intentionally open-ended; validation narrows
// fields at each document boundary below.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;
type Submission = { name: string; type: string; access_id: string; purchase_order: string; status: "Pending" | "Approved" | "Rejected"; payload: Row; file_name?: string; result_document?: string; payload_hash: string; created_at: string; reviewed_at?: string; review_note?: string };
const TTL = 90 * 24 * 60 * 60;
let redis: Redis | undefined;
function db(): Redis {
  if (redis) return redis;
  const url = process.env.KV_REST_API_URL; const token = process.env.KV_REST_API_TOKEN;
  if (!url || !token) throw new ApiRequestError("configuration_error", "Supplier portal storage is not configured.", 503);
  redis = new Redis({ url, token }); return redis;
}
function hash(value: unknown): string { return createHash("sha256").update(JSON.stringify(value)).digest("hex"); }
function submissionKey(accessId: string, type: string, idempotency: string): string { return `erp:supplier-portal:submission:${accessId}:${type}:${idempotency}`; }
function submissionIndex(accessId: string): string { return `erp:supplier-portal:submissions:${accessId}`; }
function submissionGlobalIndex(): string { return "erp:supplier-portal:submissions"; }
function stateKey(orchestrationId: string): string { return `erp:supplier-portal:state:${orchestrationId}`; }
function orchestrationIndex(): string { return "erp:supplier-portal:orchestrations"; }
function text(value: unknown): string { return String(value ?? "").trim(); }
function number(value: unknown, label: string, min = 0): number { const n = Number(value); if (!Number.isFinite(n) || n < min) throw new ApiRequestError("validation_failed", `${label} is invalid.`, 400); return n; }
function requireAccess(accessId: string): Promise<SupplierPortalAccess> { return getAccessById(accessId).then((value) => { if (!value) throw new ApiRequestError("supplier_portal_not_found", "Magic Link is invalid or expired.", 404); return value; }); }
async function withLock<T>(key: string, operation: () => Promise<T>): Promise<T> {
  const lockKey = `erp:supplier-portal:lock:${key}`;
  const claimed = await db().set(lockKey, randomUUID(), { nx: true, ex: 60 });
  if (!claimed) throw new ApiRequestError("supplier_portal_rate_limited", "This operation is already being processed.", 409, true, 2);
  try { return await operation(); } finally { await db().del(lockKey); }
}
export async function resolveSupplierEmail(supplier: string, fallback = ""): Promise<string> {
  const supplierDoc = await frappeGet<Row>("Supplier", supplier).catch(() => null);
  const direct = text(supplierDoc?.email_id);
  if (direct) return direct;
  const contacts = await frappeList<Row>("Contact", [["Contact", "link_doctype", "=", "Supplier"], ["Contact", "link_name", "=", supplier]], ["name", "email_id"], 20).catch(() => []);
  const email = contacts.map((row) => text(row.email_id)).find(Boolean);
  if (email) return email;
  if (fallback.trim()) return fallback.trim();
  throw new ApiRequestError("supplier_email_missing", `Supplier ${supplier} has no email address.`, 400);
}
async function saveSubmission(value: Submission): Promise<void> { const key = submissionKey(value.access_id, value.type, value.payload.idempotency_key); await db().set(key, value, { ex: TTL }); await db().sadd(submissionIndex(value.access_id), `${value.type}:${value.payload.idempotency_key}`); await db().expire(submissionIndex(value.access_id), TTL); await db().sadd(submissionGlobalIndex(), key); await db().expire(submissionGlobalIndex(), TTL); }
async function submissions(accessId: string): Promise<Submission[]> { const keys = await db().smembers<string[]>(submissionIndex(accessId)); const values = await Promise.all(keys.map((key) => { const split = key.indexOf(":"); return db().get<Submission>(submissionKey(accessId, key.slice(0, split), key.slice(split + 1))); })); return values.filter((v): v is Submission => Boolean(v)); }

export async function ensureSupplierPortalAccess(input: { orchestration_id: string; material_request: string; request_for_quotation: string; supplier: string; email: string; deadline_at: string; access_expires_at?: string }): Promise<{ access: SupplierPortalAccess; magic_token: string }> {
  const existing = (await getAccessesForOrchestration(input.orchestration_id)).find((v) => v.supplier === input.supplier);
  if (existing) return { access: existing, magic_token: decryptToken(existing) };
  const magic_token = randomUUID().replaceAll("-", "") + randomUUID().replaceAll("-", "");
  const access = await registerAccessForOrchestration(input.orchestration_id, {
    access_id: createHash("sha256").update(`${input.orchestration_id}:${input.supplier}`).digest("hex").slice(0, 24),
    orchestration_id: input.orchestration_id, material_request: input.material_request, supplier: input.supplier, email: input.email, request_for_quotation: input.request_for_quotation,
    magic_expires_at: input.access_expires_at ?? input.deadline_at,
    quotation_deadline_at: input.deadline_at,
    magic_token,
  });
  await db().sadd(orchestrationIndex(), input.orchestration_id);
  await db().expire(orchestrationIndex(), TTL);
  return { access, magic_token };
}
function decryptToken(access: SupplierPortalAccess): string { return decryptSupplierPortalToken(access); }

export async function processSummary(accessId: string): Promise<Row> {
  const access = await requireAccess(accessId);
  const rfq = await frappeGet<Row>("Request for Quotation", access.request_for_quotation);
  const quotes = await frappeList<Row>("Supplier Quotation", [["Supplier Quotation", "request_for_quotation", "=", access.request_for_quotation], ["Supplier Quotation", "supplier", "=", access.supplier]], ["name", "supplier", "docstatus", "grand_total", "net_total", "modified"], 100);
  const quote = quotes.find((v) => Number(v.docstatus) === 1);
  const docs = await frappeList<Row>("Purchase Order", [["Purchase Order", "custom_letron_orchestration_id", "=", access.orchestration_id], ["Purchase Order", "supplier", "=", access.supplier], ["Purchase Order", "docstatus", "=", 1]], ["name"], 20);
  const po = docs[0]?.name ? await frappeGet<Row>("Purchase Order", text(docs[0].name)) : null;
  const receipts = po ? await frappeList<Row>("Purchase Receipt", [["Purchase Receipt", "custom_letron_orchestration_id", "=", access.orchestration_id], ["Purchase Receipt", "supplier", "=", access.supplier], ["Purchase Receipt", "docstatus", "=", 1]], ["name", "docstatus", "status"], 1000) : [];
  const receiptDetails = await Promise.all(receipts.map((row) => frappeGet<Row>("Purchase Receipt", text(row.name))));
  const invoices = po ? await frappeList<Row>("Purchase Invoice", [["Purchase Invoice", "custom_letron_orchestration_id", "=", access.orchestration_id], ["Purchase Invoice", "supplier", "=", access.supplier], ["Purchase Invoice", "docstatus", "=", 1]], ["name", "docstatus", "status", "outstanding_amount"], 1000) : [];
  const invoiceDetails = await Promise.all(invoices.map((row) => frappeGet<Row>("Purchase Invoice", text(row.name))));
  const outstanding = invoiceDetails.reduce((sum, invoice) => sum + Number(invoice.outstanding_amount ?? 0), 0);
  const state = await db().get<Row>(stateKey(access.orchestration_id));
  return { process: access.orchestration_id, material_request: access.material_request, supplier: access.supplier, rfq: { name: rfq.name, status: text(rfq.status), transaction_date: text(rfq.transaction_date), items: (rfq.items ?? []).map((raw: unknown) => { const v = raw as Row; return { name: v.name, item_code: v.item_code, description: v.description, qty: v.qty, uom: v.uom, warehouse: v.warehouse }; }) }, quotation: quote ? { name: quote.name, status: "Submitted" } : null, purchase_order: po ? { name: po.name, status: Number(po.docstatus) === 1 ? "Submitted" : "Draft", transaction_date: po.transaction_date, schedule_date: po.schedule_date, currency: po.currency, items: po.items ?? [] } : null, purchase_receipt: receiptDetails.map((item) => ({ name: item.name, status: Number(item.docstatus) === 1 ? "Submitted" : "Draft", items: item.items ?? [] })), purchase_invoice: invoiceDetails.map((item) => ({ name: item.name, status: Number(item.docstatus) === 1 ? "Submitted" : "Draft", outstanding_amount: item.outstanding_amount })), payment_status: !invoiceDetails.length ? "Not Invoiced" : outstanding <= 0 ? "Paid" : "Invoiced", approval_status: text(state?.approval_status || "Waiting"), deadline_at: text(state?.deadline_at || access.quotation_deadline_at || access.magic_expires_at), submissions: { delivery: await listSubmissions(accessId, "Delivery Confirmation"), xml_invoice: await listSubmissions(accessId, "XML Invoice") } };
}

export async function submitQuotation(accessId: string, payload: Row): Promise<Row> {
  return withLock(`quotation:${accessId}`, async () => {
    const access = await requireAccess(accessId);
    const deadline = Date.parse(access.quotation_deadline_at ?? access.magic_expires_at);
    if (Number.isFinite(deadline) && Date.now() > deadline) throw new ApiRequestError("quotation_window_closed", "The quotation window is closed.", 409);
    const rfq = await frappeGet<Row>("Request for Quotation", access.request_for_quotation);
    const suppliers = (rfq.suppliers ?? []) as Row[];
    if (!suppliers.some((row) => text(row.supplier) === access.supplier)) throw new ApiRequestError("validation_failed", "Supplier is not part of the RFQ.", 400);
    const existing = (await frappeList<Row>("Supplier Quotation", [["Supplier Quotation", "request_for_quotation", "=", rfq.name], ["Supplier Quotation", "supplier", "=", access.supplier], ["Supplier Quotation", "docstatus", "=", 1]], ["name"], 5))[0];
    if (existing) return { supplier_quotation: existing.name, idempotent: true };
    if (!Array.isArray(payload.items) || !payload.items.length) throw new ApiRequestError("validation_failed", "At least one quotation item is required.", 400);
    const source = new Map<string, Row>((rfq.items ?? []).map((raw: unknown) => { const row = raw as Row; return [text(row.name), row]; }));
    const seen = new Set<string>();
    const items = payload.items.map((raw: Row) => {
      const itemName = text(raw.request_for_quotation_item);
      if (seen.has(itemName)) throw new ApiRequestError("validation_failed", "Quotation contains a duplicate RFQ item.", 400);
      seen.add(itemName);
      const item = source.get(itemName);
      if (!item) throw new ApiRequestError("validation_failed", "Quotation item is not part of the RFQ.", 400);
      return { item_code: item.item_code, qty: number(raw.qty ?? item.qty, "qty", 0.000001), uom: item.uom, warehouse: item.warehouse, rate: number(raw.rate, "rate"), request_for_quotation: rfq.name, request_for_quotation_item: item.name, material_request: item.material_request, material_request_item: item.material_request_item };
    });
    if (seen.size !== source.size) throw new ApiRequestError("validation_failed", "Every RFQ item must be quoted exactly once.", 400);
    const doc = await frappeInsert<Row>({ doctype: "Supplier Quotation", naming_series: "SQ-.YYYYMMDD.-.####", supplier: access.supplier, company: rfq.company, transaction_date: new Date().toISOString().slice(0, 10), request_for_quotation: rfq.name, custom_letron_orchestration_id: access.orchestration_id, items });
    const submitted = await frappeSubmit<Row>(doc);
    await db().set(stateKey(access.orchestration_id), { ...(await db().get<Row>(stateKey(access.orchestration_id)) ?? {}), deadline_at: access.magic_expires_at, last_quotation: submitted.name ?? doc.name }, { ex: TTL });
    return { supplier_quotation: submitted.name ?? doc.name, idempotent: false };
  });
}

export async function evaluateApprovalGate(orchestrationId: string): Promise<Row> {
  return withLock(`gate:${orchestrationId}`, async () => {
  const accesses = await getAccessesForOrchestration(orchestrationId); if (!accesses.length) throw new ApiRequestError("validation_failed", "Supplier access is missing.", 400);
  const quotes = (await Promise.all(accesses.map(async (access) => { const rows = await frappeList<Row>("Supplier Quotation", [["Supplier Quotation", "request_for_quotation", "=", access.request_for_quotation], ["Supplier Quotation", "supplier", "=", access.supplier], ["Supplier Quotation", "docstatus", "=", 1]], ["name", "supplier", "currency", "conversion_rate", "grand_total", "base_grand_total", "net_total", "modified"], 10); return rows[0] ? { ...rows[0], access } : null; }))).filter(Boolean) as Row[];
  const currencies = new Set(quotes.map((quote) => text(quote.currency)).filter(Boolean));
  if (currencies.size > 1) throw new ApiRequestError("supplier_currency_mismatch", "Supplier quotations must use the same currency before approval.", 409);
  const currentState = await db().get<Row>(stateKey(orchestrationId)) ?? {};
  const deadline = Date.parse(text(currentState.deadline_at)) || Math.min(...accesses.map((v) => Date.parse(v.quotation_deadline_at ?? v.magic_expires_at)));
  const ready = quotes.length > 0 && (quotes.length === accesses.length || Date.now() >= deadline); const selected = quotes.sort((a, b) => quoteBaseTotal(a) - quoteBaseTotal(b))[0];
  const state = { ...currentState, approval_status: ready ? "Ready" : "Waiting", selected_supplier_quotation: selected?.name, deadline_at: new Date(deadline).toISOString() };
  await db().set(stateKey(orchestrationId), state, { ex: TTL });
  return { process: orchestrationId, orchestration_id: orchestrationId, material_request: accesses[0].material_request, ready, deadline_reached: Date.now() >= deadline, submitted_count: quotes.length, supplier_count: accesses.length, approval_status: state.approval_status, selected_supplier_quotation: selected?.name, suppliers: accesses.map((v) => ({ name: v.access_id, supplier: v.supplier, status: quotes.some((q) => q.access.supplier === v.supplier) ? "Submitted" : "Waiting" })) };
  });
}

function quoteBaseTotal(quote: Row): number {
  const base = Number(quote.base_grand_total);
  if (Number.isFinite(base) && base >= 0) return base;
  const total = Number(quote.grand_total ?? quote.net_total ?? 0);
  const conversion = Number(quote.conversion_rate ?? 1);
  return Number.isFinite(total) && Number.isFinite(conversion) ? total * conversion : Number.POSITIVE_INFINITY;
}

export async function createPurchaseOrderDraft(orchestrationId: string, supplierQuotationName: string): Promise<Row> {
  return withLock(`po:${orchestrationId}`, async () => {
    const existing = (await frappeList<Row>("Purchase Order", [["Purchase Order", "custom_letron_orchestration_id", "=", orchestrationId], ["Purchase Order", "docstatus", "=", 0]], ["name"], 10))[0];
    if (existing?.name) return await frappeGet<Row>("Purchase Order", text(existing.name));
    const quotation = await frappeGet<Row>("Supplier Quotation", supplierQuotationName);
    if (Number(quotation.docstatus ?? 0) !== 1) throw new ApiRequestError("supplier_quotation_not_submitted", "The selected supplier quotation is not submitted.", 409);
    const rfqName = text(quotation.request_for_quotation);
    const rfq = await frappeGet<Row>("Request for Quotation", rfqName);
    const items = Array.isArray(quotation.items) ? quotation.items as Row[] : [];
    if (!items.length) throw new ApiRequestError("supplier_quotation_items_missing", "The selected supplier quotation has no items.", 409);
    return await frappeInsert<Row>({
      doctype: "Purchase Order", naming_series: "PO-.YYYYMMDD.-.####",
      supplier: quotation.supplier, company: quotation.company ?? rfq.company,
      transaction_date: quotation.transaction_date ?? rfq.transaction_date,
      schedule_date: quotation.schedule_date ?? rfq.schedule_date ?? quotation.transaction_date,
      currency: quotation.currency ?? rfq.currency ?? "VND", conversion_rate: quotation.conversion_rate ?? 1,
      custom_letron_orchestration_id: orchestrationId, custom_lark_approval_status: "Pending Approval",
      items: items.map((item) => ({ item_code: item.item_code, qty: item.qty, uom: item.uom, conversion_factor: item.conversion_factor, schedule_date: item.schedule_date, warehouse: item.warehouse, rate: item.rate, material_request: item.material_request, material_request_item: item.material_request_item, request_for_quotation: item.request_for_quotation ?? rfqName, request_for_quotation_item: item.request_for_quotation_item, supplier_quotation: quotation.name, supplier_quotation_item: item.name })),
    });
  });
}
export async function evaluateDueOrchestrations(): Promise<Row> {
  const ids = await db().smembers<string[]>(orchestrationIndex());
  const ready: Row[] = [];
  for (const id of ids) {
    if (!id) continue;
    const gate = await evaluateApprovalGate(id).catch(() => null);
    if (gate?.ready && gate.selected_supplier_quotation) ready.push(gate);
  }
  return { evaluated: ids.length, ready };
}

export async function createDelivery(accessId: string, payload: Row): Promise<Row> { return createSubmission(accessId, "Delivery Confirmation", payload); }
export async function uploadInvoice(accessId: string, form: FormData): Promise<Row> {
  const access = await requireAccess(accessId);
  const file = form.get("file");
  if (!(file instanceof File) || !file.name.toLowerCase().endsWith(".xml") || file.size > 5 * 1024 * 1024) throw new ApiRequestError("validation_failed", "A valid XML invoice under 5 MB is required.", 400);
  const xml = await file.text();
  if (!/^\s*<\?xml|^\s*</i.test(xml) || !/<(?:[\w-]+:)?Invoice\b/i.test(xml)) throw new ApiRequestError("validation_failed", "The uploaded file is not a valid invoice XML.", 400);
  const po = (await frappeList<Row>("Purchase Order", [["Purchase Order", "custom_letron_orchestration_id", "=", access.orchestration_id], ["Purchase Order", "supplier", "=", access.supplier], ["Purchase Order", "docstatus", "=", 1]], ["name"], 5))[0];
  if (!po?.name) throw new ApiRequestError("validation_failed", "Purchase Order is not available.", 400);
  const uploaded = await frappeUpload(file, { doctype: "Purchase Order", docname: text(po.name), folder: "Home/Attachments" });
  return createSubmission(accessId, "XML Invoice", { idempotency_key: text(form.get("idempotency_key")), file_name: file.name, file_url: uploaded.file_url, xml_hash: hash(xml), access_id: access.access_id });
}
async function createSubmission(accessId: string, type: string, payload: Row): Promise<Row> {
  return withLock(`submission:${accessId}:${type}:${text(payload.idempotency_key)}`, async () => {
    const access = await requireAccess(accessId);
    const key = text(payload.idempotency_key);
    if (!key || key.length > 128) throw new ApiRequestError("validation_failed", "idempotency_key is required.", 400);
    const existing = await db().get<Submission>(submissionKey(accessId, type, key));
    const payloadHash = hash({ ...payload, xml: type === "XML Invoice" ? hash(payload.xml) : payload.xml });
    if (existing) {
      if (existing.payload_hash !== payloadHash) throw new ApiRequestError("validation_failed", "Idempotency key was used with a different payload.", 400);
      return { submission: existing.name, status: existing.status, idempotent: true };
    }
    if (type === "XML Invoice" && text(payload.xml_hash)) {
      const duplicate = (await submissions(accessId)).find((row) => row.type === type && text(row.payload.xml_hash) === text(payload.xml_hash));
      if (duplicate) return { submission: duplicate.name, status: duplicate.status, idempotent: true };
    }
    const poRef = (await frappeList<Row>("Purchase Order", [["Purchase Order", "custom_letron_orchestration_id", "=", access.orchestration_id], ["Purchase Order", "supplier", "=", access.supplier], ["Purchase Order", "docstatus", "=", 1]], ["name"], 5))[0];
    if (!poRef) throw new ApiRequestError("validation_failed", "Purchase Order is not available.", 400);
    const po = await frappeGet<Row>("Purchase Order", text(poRef.name));
    if (type === "Delivery Confirmation") {
      if (!Array.isArray(payload.items) || !payload.items.length || !text(payload.delivery_date)) throw new ApiRequestError("validation_failed", "Delivery date and items are required.", 400);
      const ordered = new Map((po.items as Row[]).map((item) => [text(item.name), number(item.qty, "ordered quantity")]));
      const previous = await submissions(accessId);
      const used = new Map<string, number>();
      for (const prior of previous.filter((row) => row.type === type && ["Pending", "Approved"].includes(row.status))) for (const item of (prior.payload.items ?? []) as Row[]) used.set(text(item.purchase_order_item), (used.get(text(item.purchase_order_item)) ?? 0) + number(item.delivered_qty, "delivered quantity"));
      let positive = false;
      for (const item of payload.items as Row[]) {
        const name = text(item.purchase_order_item); const qty = number(item.delivered_qty, "delivered quantity");
        if (!ordered.has(name) || (used.get(name) ?? 0) + qty > ordered.get(name)!) throw new ApiRequestError("validation_failed", "Delivered quantity exceeds the remaining Purchase Order quantity.", 400);
        if (qty > 0) positive = true;
      }
      if (!positive) throw new ApiRequestError("validation_failed", "At least one delivered quantity is required.", 400);
    }
    const value: Submission = { name: `SUP-${randomUUID()}`, type, access_id: accessId, purchase_order: text(po.name), status: "Pending", payload: { ...payload, idempotency_key: key, orchestration_id: access.orchestration_id }, payload_hash: payloadHash, created_at: new Date().toISOString(), file_name: payload.file_name };
    await saveSubmission(value);
    return { submission: value.name, status: value.status, idempotent: false };
  });
}
async function listSubmissions(accessId: string, type: string): Promise<Row[]> { const all = await submissions(accessId); return all.filter((v) => v.type === type).map((v) => ({ name: v.name, submission_type: v.type, purchase_order: v.purchase_order, status: v.status, file_name: v.file_name, reviewed_at: v.reviewed_at ?? "", result_document: v.result_document })); }
export async function getSubmissions(accessId: string): Promise<Row> { return { delivery: await listSubmissions(accessId, "Delivery Confirmation"), xml_invoice: await listSubmissions(accessId, "XML Invoice") }; }
export async function revokeAccess(accessId: string): Promise<Row> { const access = await requireAccess(accessId); await updateAccess({ ...access, magic_expires_at: new Date(0).toISOString() }); return { access_id: accessId, status: "Revoked", idempotent: false }; }
export async function approvalState(orchestrationId: string, action: string, approvalId?: string): Promise<Row> {
  return withLock(`approval:${orchestrationId}`, async () => {
    const state = await db().get<Row>(stateKey(orchestrationId)) ?? {};
    const claimed = action === "claim" && state.approval_status === "Ready";
    if (claimed) state.approval_status = "Opening";
    if (action === "release" && state.approval_status === "Opening") state.approval_status = "Ready";
    if (action === "opened" && approvalId) {
      if (state.approval_id && state.approval_id !== approvalId) throw new ApiRequestError("approval_conflict", "A different approval instance already exists.", 409);
      state.approval_status = "Opened";
      state.approval_id = approvalId;
    }
    await db().set(stateKey(orchestrationId), state, { ex: TTL });
    return { process: orchestrationId, claimed, released: action === "release", approval_status: state.approval_status, approval_id: state.approval_id, idempotent: action === "opened" && state.approval_id === approvalId };
  });
}
async function receivedByPoItem(poName: string, orchestrationId: string): Promise<Map<string, number>> {
  const rows = await frappeList<Row>("Purchase Receipt", [["Purchase Receipt", "docstatus", "=", 1], ["Purchase Receipt", "custom_letron_orchestration_id", "=", orchestrationId]], ["name"], 1000);
  const totals = new Map<string, number>();
  for (const row of rows) {
    const receipt = await frappeGet<Row>("Purchase Receipt", text(row.name));
    for (const item of (receipt.items ?? []) as Row[]) if (text(item.purchase_order) === poName) totals.set(text(item.purchase_order_item), (totals.get(text(item.purchase_order_item)) ?? 0) + number(item.qty, "received quantity"));
  }
  return totals;
}

export async function reviewSubmission(submissionId: string, decision: "Approved" | "Rejected", note = ""): Promise<Row> {
  const keys = await db().smembers<string[]>(submissionGlobalIndex());
  const all = await Promise.all(keys.map((key) => db().get<Submission>(key)));
  const indexed = all.find((row) => row?.name === submissionId);
  if (!indexed) throw new ApiRequestError("not_found", "Submission was not found.", 404);
  return withLock(`po-review:${indexed.purchase_order}`, async () => {
    const value = await db().get<Submission>(submissionKey(indexed.access_id, indexed.type, text(indexed.payload.idempotency_key))) ?? indexed;
    if (value.status !== "Pending") return { submission: value.name, status: value.status, result_document: value.result_document, idempotent: true };
    if (decision === "Rejected") {
      value.status = "Rejected"; value.review_note = note; value.reviewed_at = new Date().toISOString(); await saveSubmission(value);
      return { submission: value.name, status: value.status, idempotent: false };
    }
    const access = await requireAccess(value.access_id);
    const po = await frappeGet<Row>("Purchase Order", value.purchase_order);
    let doc: Row;
    if (value.type === "Delivery Confirmation") {
      const rows = (value.payload.items as Row[]).map((row) => {
        const source = (po.items as Row[]).find((item) => text(item.name) === text(row.purchase_order_item));
        if (!source) throw new ApiRequestError("validation_failed", "Delivery item is not part of the Purchase Order.", 400);
        return { item_code: source.item_code, qty: number(row.delivered_qty, "delivered_qty"), uom: source.uom, rate: source.rate, purchase_order: po.name, purchase_order_item: source.name, warehouse: source.warehouse, serial_no: row.serial_no, batch_no: row.batch_no };
      });
      doc = await frappeInsert<Row>({ doctype: "Purchase Receipt", naming_series: "GRN-.YYYYMMDD.-.####", supplier: po.supplier, company: po.company, custom_letron_orchestration_id: access.orchestration_id, posting_date: value.payload.delivery_date, items: rows });
    } else {
      const received = await receivedByPoItem(text(po.name), access.orchestration_id);
      for (const item of po.items as Row[]) if ((received.get(text(item.name)) ?? 0) < number(item.qty, "ordered quantity")) throw new ApiRequestError("invoice_waiting_for_receipt", "All Purchase Order quantity must be received before invoicing.", 409);
      doc = await frappeInsert<Row>({ doctype: "Purchase Invoice", naming_series: "INV-.YYYYMMDD.-.####", supplier: po.supplier, company: po.company, custom_letron_orchestration_id: access.orchestration_id, items: (po.items as Row[]).map((item) => ({ item_code: item.item_code, qty: item.qty, uom: item.uom, rate: item.rate, purchase_order: po.name, purchase_order_item: item.name })) });
    }
    const submitted = await frappeSubmit<Row>(doc);
    value.status = "Approved"; value.result_document = text(submitted.name ?? doc.name); value.review_note = note; value.reviewed_at = new Date().toISOString(); await saveSubmission(value);
    return { submission: value.name, status: value.status, result_document: value.result_document, idempotent: false };
  });
}
