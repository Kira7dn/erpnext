import "server-only";

import { createHash, randomUUID } from "node:crypto";
import { Redis } from "@upstash/redis";
import { ApiRequestError } from "./api-error";
import { frappeCreateSupplierQuotation, frappeDocumentAction, frappeGet, frappeInsert, frappeMakePurchaseOrder, frappeUpdate, frappeUpload, type ErpPurchaseOrderDraft } from "./frappe-client";
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
type MutationResult = { document_name: string; payload_hash: string; created_at: string };
const TTL = 90 * 24 * 60 * 60;
let redis: Redis | undefined;
function db(): Redis {
  if (redis) return redis;
  const url = process.env.KV_REST_API_URL; const token = process.env.KV_REST_API_TOKEN;
  if (!url || !token) throw new ApiRequestError("configuration_error", "Supplier portal storage is not configured.", 503);
  redis = new Redis({ url, token }); return redis;
}
function hash(value: unknown): string { return createHash("sha256").update(JSON.stringify(value)).digest("hex"); }
function record(value: unknown): Row { return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Row : {}; }
function mutationKey(accessId: string, type: string, idempotency: string): string { return `erp:supplier-portal:mutation:${accessId}:${type}:${idempotency}`; }
function stateKey(orchestrationId: string): string { return `erp:supplier-portal:state:${orchestrationId}`; }
function orchestrationIndex(): string { return "erp:supplier-portal:orchestrations"; }
function text(value: unknown): string { return String(value ?? "").trim(); }
function number(value: unknown, label: string, min = 0): number { const n = Number(value); if (!Number.isFinite(n) || n < min) throw new ApiRequestError("validation_failed", `${label} is invalid.`, 400); return n; }
export function supplierQuotationRfqName(quotation: Row): string {
  const items = Array.isArray(quotation.items) ? quotation.items as Row[] : [];
  const names = items.map((item) => text(item.request_for_quotation));
  if (!items.length || names.some((name) => !name) || new Set(names).size !== 1) {
    throw new ApiRequestError("supplier_quotation_mapping_mismatch", "Supplier quotation items do not reference one RFQ.", 409);
  }
  return names[0];
}
function requireAccess(accessId: string): Promise<SupplierPortalAccess> { return getAccessById(accessId).then((value) => { if (!value) throw new ApiRequestError("supplier_portal_not_found", "Magic Link is invalid or expired.", 404); return value; }); }
async function withLock<T>(key: string, operation: () => Promise<T>): Promise<T> {
  const lockKey = `erp:supplier-portal:lock:${key}`;
  const claimed = await db().set(lockKey, randomUUID(), { nx: true, ex: 60 });
  if (!claimed) throw new ApiRequestError("supplier_portal_rate_limited", "This operation is already being processed.", 409, true, 2);
  try { return await operation(); } finally { await db().del(lockKey); }
}
export async function resolveSupplierEmail(supplier: string): Promise<string> {
  const supplierDoc = await frappeGet<Row>("Supplier", supplier);
  const email = text(supplierDoc.email_id);
  if (!email) throw new ApiRequestError("supplier_email_missing", `Supplier ${supplier} has no email address.`, 400);
  return email;
}
async function mutation(accessId: string, type: string, idempotency: string): Promise<MutationResult | null> { return db().get<MutationResult>(mutationKey(accessId, type, idempotency)); }
async function saveMutation(accessId: string, type: string, idempotency: string, value: MutationResult): Promise<void> { await db().set(mutationKey(accessId, type, idempotency), value, { ex: TTL }); }

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
  const state = await db().get<Row>(stateKey(access.orchestration_id)) ?? {};
  const rfq = await frappeGet<Row>("Request for Quotation", access.request_for_quotation);
  if (text(rfq.custom_letron_orchestration_id) !== access.orchestration_id) throw new ApiRequestError("request_for_quotation_mapping_mismatch", "Request for Quotation does not belong to this process.", 409);
  const quotationNames = record(state.quotations);
  const quotationName = text(quotationNames[access.supplier]);
  const quote = quotationName ? await frappeGet<Row>("Supplier Quotation", quotationName) : null;
  if (quote && (text(quote.custom_letron_orchestration_id) !== access.orchestration_id || supplierQuotationRfqName(quote) !== access.request_for_quotation || text(quote.supplier) !== access.supplier || Number(quote.docstatus ?? 0) !== 1)) {
    throw new ApiRequestError("supplier_quotation_mapping_mismatch", "Supplier quotation does not belong to this process.", 409);
  }
  const poName = text(state.purchase_order);
  const po = poName ? await frappeGet<Row>("Purchase Order", poName) : null;
  if (po && (text(po.custom_letron_orchestration_id) !== access.orchestration_id || text(po.supplier) !== access.supplier)) {
    throw new ApiRequestError("purchase_order_mapping_mismatch", "Purchase Order does not belong to this process.", 409);
  }
  const receiptNames = Array.isArray(state.purchase_receipts) ? state.purchase_receipts.map(text).filter(Boolean) : [];
  const receiptDetails = await Promise.all(receiptNames.map((name: string) => frappeGet<Row>("Purchase Receipt", name)));
  const invoiceNames = Array.isArray(state.purchase_invoices) ? state.purchase_invoices.map(text).filter(Boolean) : [];
  const invoiceDetails = await Promise.all(invoiceNames.map((name: string) => frappeGet<Row>("Purchase Invoice", name)));
  const outstanding = invoiceDetails.reduce((sum, invoice) => sum + Number(invoice.outstanding_amount ?? 0), 0);
  return { process: access.orchestration_id, material_request: access.material_request, supplier: access.supplier, rfq: { name: rfq.name, status: text(rfq.status), transaction_date: text(rfq.transaction_date), items: (rfq.items ?? []).map((raw: unknown) => { const v = raw as Row; return { name: v.name, item_code: v.item_code, description: v.description, qty: v.qty, uom: v.uom, warehouse: v.warehouse }; }) }, quotation: quote ? { name: quote.name, status: "Submitted" } : null, purchase_order: po ? { name: po.name, status: Number(po.docstatus) === 1 ? "Submitted" : "Draft", transaction_date: po.transaction_date, schedule_date: po.schedule_date, currency: po.currency, grand_total: po.grand_total, items: po.items ?? [] } : null, purchase_receipt: receiptDetails.map((item) => ({ name: item.name, status: Number(item.docstatus) === 1 ? "Submitted" : "Draft", items: item.items ?? [] })), purchase_invoice: invoiceDetails.map((item) => ({ name: item.name, status: Number(item.docstatus) === 1 ? "Submitted" : "Draft", outstanding_amount: item.outstanding_amount })), payment_status: !invoiceDetails.length ? "Not Invoiced" : outstanding <= 0 ? "Paid" : "Invoiced", approval_status: text(state?.approval_status || "Waiting"), deadline_at: text(state?.deadline_at || access.quotation_deadline_at || access.magic_expires_at), submissions: { delivery: receiptDetails.map((item) => ({ name: item.name, submission_type: "Purchase Receipt", purchase_order: po?.name ?? "", status: "Submitted", result_document: item.name })), xml_invoice: invoiceDetails.map((item) => ({ name: item.name, submission_type: "Purchase Invoice", purchase_order: po?.name ?? "", status: "Submitted", result_document: item.name })) } };
}

export async function submitQuotation(accessId: string, payload: Row): Promise<Row> {
  return withLock(`quotation:${accessId}`, async () => {
    const access = await requireAccess(accessId);
  const deadline = Date.parse(access.quotation_deadline_at ?? "");
  if (!Number.isFinite(deadline)) throw new ApiRequestError("quotation_deadline_missing", "Quotation deadline is missing.", 409);
    if (Number.isFinite(deadline) && Date.now() > deadline) throw new ApiRequestError("quotation_window_closed", "The quotation window is closed.", 409);
    const rfq = await frappeGet<Row>("Request for Quotation", access.request_for_quotation);
    const suppliers = (rfq.suppliers ?? []) as Row[];
    if (!suppliers.some((row) => text(row.supplier) === access.supplier)) throw new ApiRequestError("validation_failed", "Supplier is not part of the RFQ.", 400);
    const currentState = await db().get<Row>(stateKey(access.orchestration_id)) ?? {};
    const quotations = record(currentState.quotations);
    const existingName = text(quotations[access.supplier]);
    if (existingName) {
      const existing = await frappeGet<Row>("Supplier Quotation", existingName);
      if (text(existing.custom_letron_orchestration_id) !== access.orchestration_id || supplierQuotationRfqName(existing) !== rfq.name || text(existing.supplier) !== access.supplier || Number(existing.docstatus ?? 0) !== 1) {
        throw new ApiRequestError("supplier_quotation_mapping_mismatch", "Stored supplier quotation does not belong to this process.", 409);
      }
      return { supplier_quotation: existingName, idempotent: true };
    }
    if (!Array.isArray(payload.items) || !payload.items.length) throw new ApiRequestError("validation_failed", "At least one quotation item is required.", 400);
    const source = new Map<string, Row>((rfq.items ?? []).map((raw: unknown) => { const row = raw as Row; return [text(row.name), row]; }));
    const seen = new Set<string>();
    const items = payload.items.map((raw: Row) => {
      const itemName = text(raw.request_for_quotation_item);
      if (seen.has(itemName)) throw new ApiRequestError("validation_failed", "Quotation contains a duplicate RFQ item.", 400);
      seen.add(itemName);
      const item = source.get(itemName);
      if (!item) throw new ApiRequestError("validation_failed", "Quotation item is not part of the RFQ.", 400);
      const expectedDeliveryDate = text(item.schedule_date);
      if (!expectedDeliveryDate) throw new ApiRequestError("quotation_item_schedule_date_missing", "RFQ item schedule date is missing.", 409);
      return { item_code: item.item_code, qty: number(raw.qty, "qty", 0.000001), uom: item.uom, warehouse: item.warehouse, rate: number(raw.rate, "rate"), expected_delivery_date: expectedDeliveryDate, request_for_quotation: rfq.name, request_for_quotation_item: item.name, material_request: item.material_request, material_request_item: item.material_request_item };
    });
    if (seen.size !== source.size) throw new ApiRequestError("validation_failed", "Every RFQ item must be quoted exactly once.", 400);
    const quotationPayload: Record<string, unknown> = {
      doctype: "Supplier Quotation",
      naming_series: "SQ-.YYYYMMDD.-.####",
      supplier: access.supplier,
      company: rfq.company,
      transaction_date: new Date().toISOString().slice(0, 10),
      custom_letron_orchestration_id: access.orchestration_id,
      items,
    };
    const currency = text(rfq.currency);
    const conversionRate = Number(rfq.conversion_rate);
    if (currency) quotationPayload.currency = currency;
    if (Number.isFinite(conversionRate) && conversionRate > 0) quotationPayload.conversion_rate = conversionRate;
    const doc = await frappeCreateSupplierQuotation(quotationPayload);
    const quotationName = text(doc.name);
    if (!quotationName) throw new ApiRequestError("supplier_quotation_missing", "ERPNext did not return the Supplier Quotation name.", 502);
    await frappeDocumentAction<Row>("Supplier Quotation", quotationName, "submit");
    await db().set(stateKey(access.orchestration_id), { ...(await db().get<Row>(stateKey(access.orchestration_id)) ?? {}), deadline_at: access.magic_expires_at, quotations: { ...quotations, [access.supplier]: quotationName } }, { ex: TTL });
    return { supplier_quotation: quotationName, idempotent: false };
  });
}

export async function evaluateApprovalGate(orchestrationId: string): Promise<Row> {
  return withLock(`gate:${orchestrationId}`, async () => {
  const accesses = await getAccessesForOrchestration(orchestrationId); if (!accesses.length) throw new ApiRequestError("validation_failed", "Supplier access is missing.", 400);
  const state = await db().get<Row>(stateKey(orchestrationId)) ?? {};
  const quotations = record(state.quotations);
  const quotes = (await Promise.all(accesses.map(async (access) => {
    const name = text(quotations[access.supplier]);
    if (!name) return null;
    const quote = await frappeGet<Row>("Supplier Quotation", name);
    if (text(quote.custom_letron_orchestration_id) !== orchestrationId || supplierQuotationRfqName(quote) !== access.request_for_quotation || text(quote.supplier) !== access.supplier || Number(quote.docstatus ?? 0) !== 1) throw new ApiRequestError("supplier_quotation_mapping_mismatch", "Supplier quotation does not belong to this process.", 409);
    return { ...quote, access };
  }))).filter(Boolean) as Row[];
  const currencies = new Set(quotes.map((quote) => text(quote.currency)).filter(Boolean));
  if (currencies.size > 1) throw new ApiRequestError("supplier_currency_mismatch", "Supplier quotations must use the same currency before approval.", 409);
  const currentState = state;
  const deadline = Date.parse(text(currentState.deadline_at));
  if (!Number.isFinite(deadline)) throw new ApiRequestError("quotation_deadline_missing", "Quotation deadline is missing.", 409);
  const ready = quotes.length > 0 && (quotes.length === accesses.length || Date.now() >= deadline); const selected = quotes.sort((a, b) => quoteBaseTotal(a) - quoteBaseTotal(b))[0];
  const nextState = { ...currentState, approval_status: ready ? "Ready" : "Waiting", selected_supplier_quotation: selected?.name, deadline_at: new Date(deadline).toISOString() };
  await db().set(stateKey(orchestrationId), nextState, { ex: TTL });
  return { process: orchestrationId, orchestration_id: orchestrationId, material_request: accesses[0].material_request, ready, deadline_reached: Date.now() >= deadline, submitted_count: quotes.length, supplier_count: accesses.length, approval_status: nextState.approval_status, selected_supplier_quotation: selected?.name, suppliers: accesses.map((v) => ({ name: v.access_id, supplier: v.supplier, status: quotes.some((q) => q.access.supplier === v.supplier) ? "Submitted" : "Waiting" })) };
  });
}

function quoteBaseTotal(quote: Row): number {
  const base = Number(quote.base_grand_total);
  if (!Number.isFinite(base) || base < 0) throw new ApiRequestError("supplier_quotation_total_missing", "Supplier quotation base total is missing.", 409);
  return base;
}

export async function createPurchaseOrderDraft(orchestrationId: string, supplierQuotationName: string): Promise<Row> {
  return withLock(`po:${orchestrationId}`, async () => {
    const currentState = await db().get<Row>(stateKey(orchestrationId)) ?? {};
    const existingName = text(currentState.purchase_order);
    if (existingName) {
      const existing = await frappeGet<Row>("Purchase Order", existingName);
      if (text(existing.custom_letron_orchestration_id) !== orchestrationId || Number(existing.docstatus ?? 0) !== 0) throw new ApiRequestError("purchase_order_mapping_mismatch", "Stored Purchase Order does not belong to this process.", 409);
      return existing;
    }
    const quotation = await frappeGet<Row>("Supplier Quotation", supplierQuotationName);
    if (Number(quotation.docstatus) !== 1 || text(quotation.custom_letron_orchestration_id) !== orchestrationId) throw new ApiRequestError("supplier_quotation_mapping_mismatch", "The selected supplier quotation does not belong to this process.", 409);
    const created: ErpPurchaseOrderDraft = await frappeMakePurchaseOrder(supplierQuotationName);
    const name = text(created.name);
    if (!name) throw new ApiRequestError("purchase_order_missing", "ERPNext did not return the Purchase Order name.", 502);
    await frappeUpdate("Purchase Order", name, { custom_letron_orchestration_id: orchestrationId, custom_lark_approval_status: "Pending Approval" });
    await db().set(stateKey(orchestrationId), { ...currentState, purchase_order: name }, { ex: TTL });
    return created;
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

async function getSubmittedPurchaseOrder(access: SupplierPortalAccess): Promise<Row> {
  const state = await db().get<Row>(stateKey(access.orchestration_id)) ?? {};
  const name = text(state.purchase_order);
  if (!name) throw new ApiRequestError("validation_failed", "Purchase Order is not available.", 400);
  const po = await frappeGet<Row>("Purchase Order", name);
  if (text(po.custom_letron_orchestration_id) !== access.orchestration_id || text(po.supplier) !== access.supplier || Number(po.docstatus ?? 0) !== 1) throw new ApiRequestError("purchase_order_mapping_mismatch", "Purchase Order does not belong to this process.", 409);
  return po;
}
function mutationInput(accessId: string, type: string, key: string, payload: unknown): { key: string; payloadHash: string } {
  const normalized = text(key);
  if (!normalized || normalized.length > 128) throw new ApiRequestError("validation_failed", "idempotency_key is required.", 400);
  return { key: normalized, payloadHash: hash(payload) };
}
export async function createDelivery(accessId: string, payload: Row): Promise<Row> {
  const access = await requireAccess(accessId);
  const input = mutationInput(accessId, "Purchase Receipt", text(payload.idempotency_key), payload);
  return withLock(`delivery:${accessId}:${input.key}`, async () => {
    const existing = await mutation(accessId, "Purchase Receipt", input.key);
    if (existing) {
      if (existing.payload_hash !== input.payloadHash) throw new ApiRequestError("validation_failed", "Idempotency key was used with a different payload.", 400);
      return { submission: existing.document_name, purchase_receipt: existing.document_name, status: "Submitted", idempotent: true };
    }
    if (!Array.isArray(payload.items) || !payload.items.length || !text(payload.delivery_date)) throw new ApiRequestError("validation_failed", "Delivery date and items are required.", 400);
    const po = await getSubmittedPurchaseOrder(access);
    const ordered = new Map((po.items as Row[]).map((item) => [text(item.name), number(item.qty, "ordered quantity")]));
    const received = await receivedByPoItem(text(po.name), access.orchestration_id);
    const seen = new Set<string>();
    let positive = false;
    const items = (payload.items as Row[]).map((item) => {
      const name = text(item.purchase_order_item); const qty = number(item.delivered_qty, "delivered quantity");
      if (seen.has(name) || !ordered.has(name) || (received.get(name)?.qty ?? 0) + qty > ordered.get(name)!) throw new ApiRequestError("validation_failed", "Delivered quantity exceeds the remaining Purchase Order quantity.", 400);
      seen.add(name); if (qty > 0) positive = true;
      const source = (po.items as Row[]).find((candidate) => text(candidate.name) === name)!;
      return { item_code: source.item_code, qty, uom: source.uom, rate: source.rate, purchase_order: po.name, purchase_order_item: source.name, warehouse: source.warehouse, serial_no: item.serial_no, batch_no: item.batch_no };
    });
    if (!positive) throw new ApiRequestError("validation_failed", "At least one delivered quantity is required.", 400);
    const frappeKey = hash(`${accessId}:Purchase Receipt:${input.key}`).slice(0, 64);
    const doc = await frappeInsert<Row>({ doctype: "Purchase Receipt", naming_series: "GRN-.YYYYMMDD.-.####", supplier: po.supplier, company: po.company, custom_letron_orchestration_id: access.orchestration_id, posting_date: text(payload.delivery_date), items }, `${frappeKey}:insert`);
    const submitted = await frappeDocumentAction<Row>("Purchase Receipt", text(doc.name), "submit");
    const documentName = text(submitted.name);
    if (!documentName) throw new ApiRequestError("purchase_receipt_missing", "ERPNext did not return the Purchase Receipt name.", 502);
    await saveMutation(accessId, "Purchase Receipt", input.key, { document_name: documentName, payload_hash: input.payloadHash, created_at: new Date().toISOString() });
    const state = await db().get<Row>(stateKey(access.orchestration_id)) ?? {};
    const receipts = Array.isArray(state.purchase_receipts) ? state.purchase_receipts.map(text).filter(Boolean) : [];
    await db().set(stateKey(access.orchestration_id), { ...state, purchase_receipts: [...new Set([...receipts, documentName])] }, { ex: TTL });
    return { submission: documentName, purchase_receipt: documentName, status: "Submitted", idempotent: false };
  });
}
export async function uploadInvoice(accessId: string, form: FormData): Promise<Row> {
  const access = await requireAccess(accessId); const file = form.get("file");
  if (!(file instanceof File) || !file.name.toLowerCase().endsWith(".xml") || file.size > 5 * 1024 * 1024) throw new ApiRequestError("validation_failed", "A valid XML invoice under 5 MB is required.", 400);
  const xml = await file.text();
  if (!/^\s*<\?xml|^\s*</i.test(xml) || !/<(?:[\w-]+:)?Invoice\b/i.test(xml)) throw new ApiRequestError("validation_failed", "The uploaded file is not a valid invoice XML.", 400);
  const key = text(form.get("idempotency_key")); const input = mutationInput(accessId, "Purchase Invoice", key, { invoice_number: form.get("invoice_number"), invoice_date: form.get("invoice_date"), invoice_total: form.get("invoice_total"), xml_hash: hash(xml) });
  return withLock(`invoice:${accessId}:${input.key}`, async () => {
    const existing = await mutation(accessId, "Purchase Invoice", input.key);
    if (existing) {
      if (existing.payload_hash !== input.payloadHash) throw new ApiRequestError("validation_failed", "Idempotency key was used with a different payload.", 400);
      return { submission: existing.document_name, purchase_invoice: existing.document_name, status: "Submitted", idempotent: true };
    }
    const po = await getSubmittedPurchaseOrder(access);
    const received = await receivedByPoItem(text(po.name), access.orchestration_id);
    for (const item of po.items as Row[]) if ((received.get(text(item.name))?.qty ?? 0) < number(item.qty, "ordered quantity")) throw new ApiRequestError("invoice_waiting_for_receipt", "All Purchase Order quantity must be received before invoicing.", 409);
    const invoiceNumber = text(form.get("invoice_number"));
    const invoiceDate = text(form.get("invoice_date"));
    const xmlTotal = Number(text(form.get("invoice_total")));
    const expectedTotal = Number(po.grand_total);
    if (!invoiceNumber || !invoiceDate || !Number.isFinite(xmlTotal) || !Number.isFinite(expectedTotal)) throw new ApiRequestError("validation_failed", "Invoice number, date and total are required.", 400);
    if (Math.abs(xmlTotal - expectedTotal) > 0.01) throw new ApiRequestError("validation_failed", "Invoice total does not match the Purchase Order.", 400);
    const uploaded = await frappeUpload(file, { doctype: "Purchase Order", docname: text(po.name), folder: "Home/Attachments" });
    const frappeKey = hash(`${accessId}:Purchase Invoice:${input.key}`).slice(0, 64);
    const doc = await frappeInsert<Row>({ doctype: "Purchase Invoice", naming_series: "INV-.YYYYMMDD.-.####", supplier: po.supplier, company: po.company, bill_no: invoiceNumber, bill_date: invoiceDate, custom_letron_orchestration_id: access.orchestration_id, items: (po.items as Row[]).map((item) => { const receipt = received.get(text(item.name)); if (!receipt) throw new ApiRequestError("invoice_waiting_for_receipt", "All Purchase Order quantity must be received before invoicing.", 409); return { item_code: item.item_code, qty: item.qty, uom: item.uom, rate: item.rate, purchase_order: po.name, purchase_order_item: item.name, purchase_receipt: receipt.purchase_receipt, purchase_receipt_item: receipt.purchase_receipt_item }; }) }, `${frappeKey}:insert`);
    const submitted = await frappeDocumentAction<Row>("Purchase Invoice", text(doc.name), "submit");
    const documentName = text(submitted.name);
    if (!documentName) throw new ApiRequestError("purchase_invoice_missing", "ERPNext did not return the Purchase Invoice name.", 502);
    await saveMutation(accessId, "Purchase Invoice", input.key, { document_name: documentName, payload_hash: input.payloadHash, created_at: new Date().toISOString() });
    const state = await db().get<Row>(stateKey(access.orchestration_id)) ?? {};
    const invoices = Array.isArray(state.purchase_invoices) ? state.purchase_invoices.map(text).filter(Boolean) : [];
    await db().set(stateKey(access.orchestration_id), { ...state, purchase_invoices: [...new Set([...invoices, documentName])] }, { ex: TTL });
    return { submission: documentName, purchase_invoice: documentName, file_url: uploaded.file_url, status: "Submitted", idempotent: false };
  });
}
export async function getSubmissions(accessId: string): Promise<Row> { const summary = await processSummary(accessId); return summary.submissions as Row; }
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
type ReceivedPoItem = { qty: number; purchase_receipt: string; purchase_receipt_item: string };

async function receivedByPoItem(poName: string, orchestrationId: string): Promise<Map<string, ReceivedPoItem>> {
  const state = await db().get<Row>(stateKey(orchestrationId)) ?? {};
  const names = Array.isArray(state.purchase_receipts) ? state.purchase_receipts.map(text).filter(Boolean) : [];
  const totals = new Map<string, ReceivedPoItem>();
  for (const name of names) {
    const receipt = await frappeGet<Row>("Purchase Receipt", name);
    if (text(receipt.custom_letron_orchestration_id) !== orchestrationId || Number(receipt.docstatus ?? 0) !== 1) throw new ApiRequestError("purchase_receipt_mapping_mismatch", "Purchase Receipt does not belong to this process.", 409);
    for (const item of (receipt.items ?? []) as Row[]) if (text(item.purchase_order) === poName) {
      const key = text(item.purchase_order_item);
      const current = totals.get(key);
      totals.set(key, {
        qty: (current?.qty ?? 0) + number(item.qty, "received quantity"),
        purchase_receipt: current?.purchase_receipt ?? text(receipt.name),
        purchase_receipt_item: current?.purchase_receipt_item ?? text(item.name),
      });
    }
  }
  return totals;
}
