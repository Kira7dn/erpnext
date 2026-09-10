import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

type Json = Record<string, unknown> | unknown[] | string | number | boolean | null;

const root = resolve(import.meta.dirname, "..");
const erpBaseUrl = process.env.ERP_BASE_URL ?? "http://localhost:3001";
const portalBaseUrl = process.env.PORTAL_BASE_URL ?? "http://localhost:3000";
const supplierPortalPublicBaseUrl = process.env.LETRON_SUPPLIER_PORTAL_PUBLIC_BASE_URL ?? "http://localhost:3001";
const item1 = process.env.MR_ITEM_1 ?? "ACCEPTANCE-LOCAL-f7aa6b9e-Item";
let item2 = process.env.MR_ITEM_2?.trim() ?? "";
const supplier1 = process.env.MR_SUPPLIER_1?.trim() || "Link Strategy";
const supplier2 = process.env.MR_SUPPLIER_2?.trim() || "";
const supplierEmail = process.env.MR_SUPPLIER_EMAIL?.trim() || "leducanh@ledb.vn";
const authBaseUrl = process.env.AUTH_BASE_URL ?? "http://localhost:3000";
const idempotencyKey = `${process.env.MR_IDEMPOTENCY_KEY?.trim() || "real-mr-approval"}-${Date.now()}`;

function object(value: Json): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function apiData(value: Json): Json {
  const row = object(value);
  if (!("data" in row)) throw new Error("API response data is missing");
  return row.data as Json;
}

function text(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

async function env(name: string): Promise<string> {
  const content = await readFile(resolve(root, ".env"), "utf8");
  const line = content.split(/\r?\n/).find((entry) => new RegExp(`^\\s*${name}\\s*=`).test(entry));
  const value = line?.replace(new RegExp(`^\\s*${name}\\s*=\\s*`), "").trim().replace(/^['"]|['"]$/g, "");
  if (!value) throw new Error(`${name} is missing from .env`);
  return value;
}

async function request(url: string, init: RequestInit = {}): Promise<{ status: number; body: Json; raw: string; cookie: string }> {
  const response = await fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json; charset=utf-8" } : {}),
      ...init.headers,
    },
  });
  const raw = await response.text();
  let body: Json = null;
  try { body = raw ? JSON.parse(raw) as Json : null; } catch { body = raw; }
  return { status: response.status, body, raw, cookie: response.headers.get("set-cookie")?.split(";", 1)[0] ?? "" };
}

async function latestEmail(subject: string, after: string, predicate: (message: string, recipients: string) => boolean = () => true): Promise<{ message: string; recipients: string }> {
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const response = await request(`${authBaseUrl}/api/internal/lark-mail/latest?subject=${encodeURIComponent(subject)}&after=${encodeURIComponent(after)}`, { headers: { Authorization: `Bearer ${await env("LETRON_API_KEY")}` } });
    if (response.status !== 200) throw new Error(`Lark Mail readback failed (${response.status}): ${response.raw}`);
    const rows = apiData(response.body);
    const items = Array.isArray(rows) ? rows : [];
    const row = items.find((item) => text(object(item as Json).message).trim() && predicate(text(object(item as Json).message), text(object(item as Json).recipients)));
    if (row) return { message: text(object(row as Json).message), recipients: text(object(row as Json).recipients) };
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 1000));
  }
  throw new Error(`Lark Mail readback did not contain subject: ${subject}`);
}

function tokenFromEmail(message: string): string {
  const match = message.match(/\/supplier\/([A-Za-z0-9_-]{40,})/);
  if (!match) throw new Error("Magic Link was not found in access email");
  return match[1];
}

function assertMagicLinkOrigin(message: string, supplier: string): string {
  const match = message.match(/https?:\/\/[^\s]+\/supplier\/[A-Za-z0-9_-]{40,}/);
  if (!match) throw new Error(`Magic Link URL was not found for ${supplier}`);
  const actual = new URL(match[0]);
  const expected = new URL(supplierPortalPublicBaseUrl);
  if (actual.origin !== expected.origin || !actual.pathname.startsWith("/supplier/")) {
    throw new Error(`Magic Link public endpoint mismatch for ${supplier}: expected=${expected.origin}, actual=${actual.origin}`);
  }
  return match[0];
}

function otpFromEmail(message: string): string {
  const match = message.match(/\b(\d{6})\b/);
  if (!match) throw new Error("OTP was not found in OTP email");
  return match[1];
}

async function supplierFlow(
  supplier: string,
  accessEmailAfter: string,
  rate: number,
  usedTokens: Set<string>,
): Promise<{ quotation: string; gate: Record<string, unknown>; approval: Record<string, unknown>; accessEmail: string; otpEmail: string; sessionCookie: string; otpReplayRejected: boolean; otpLockRejections: number }> {
  const accessEmail = await latestEmail("Letron Supplier Portal access", accessEmailAfter, (message) => {
    const token = tokenFromEmail(message);
    return !usedTokens.has(token);
  });
  assertMagicLinkOrigin(accessEmail.message, supplier);
  const magicToken = tokenFromEmail(accessEmail.message);
  if (!accessEmail.recipients.toLowerCase().includes(supplierEmail.toLowerCase())) {
    throw new Error(`Magic Link email recipient mismatch for ${supplier}: ${accessEmail.recipients}`);
  }
  usedTokens.add(magicToken);
  const otpEmailAfter = new Date().toISOString();
  const otpRequested = await request(`${erpBaseUrl}/api/supplier/${encodeURIComponent(magicToken)}/otp/request`, { method: "POST" });
  if (otpRequested.status !== 200) throw new Error(`OTP request failed for ${supplier} (${otpRequested.status}): ${otpRequested.raw}`);
  const duplicateOtpRequest = await request(`${erpBaseUrl}/api/supplier/${encodeURIComponent(magicToken)}/otp/request`, { method: "POST" });
  const duplicateOtpData = object(duplicateOtpRequest.body);
  if (duplicateOtpRequest.status !== 429 || text(duplicateOtpData.error) !== "supplier_otp_rate_limited" || Number(duplicateOtpData.retry_after_seconds ?? 0) <= 0) {
    throw new Error(`OTP resend rate limit contract failed for ${supplier}: ${duplicateOtpRequest.raw}`);
  }
  const otpEmail = await latestEmail("Letron Supplier Portal OTP", otpEmailAfter, (_message, recipients) => recipients === accessEmail.recipients);
  const otp = otpFromEmail(otpEmail.message);
  let otpLockRejections = 0;
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    const invalidOtp = otp === "000000" ? "999999" : "000000";
    const wrong = await request(`${erpBaseUrl}/api/supplier/${encodeURIComponent(magicToken)}/otp/verify`, {
      method: "POST",
      body: JSON.stringify({ otp: invalidOtp }),
    });
    if (wrong.status === 200) throw new Error(`Invalid OTP was accepted for ${supplier} on attempt ${attempt}`);
    otpLockRejections += 1;
  }
  const locked = await request(`${erpBaseUrl}/api/supplier/${encodeURIComponent(magicToken)}/otp/verify`, {
    method: "POST",
    body: JSON.stringify({ otp }),
  });
  if (locked.status === 200) throw new Error(`OTP was accepted after the attempt limit for ${supplier}`);
  await new Promise((resolveDelay) => setTimeout(resolveDelay, 16_000));
  const replacementOtpAfter = new Date().toISOString();
  const replacementRequested = await request(`${erpBaseUrl}/api/supplier/${encodeURIComponent(magicToken)}/otp/request`, { method: "POST" });
  if (replacementRequested.status !== 200) throw new Error(`OTP replacement request failed for ${supplier} (${replacementRequested.status}): ${replacementRequested.raw}`);
  const replacementEmail = await latestEmail("Letron Supplier Portal OTP", replacementOtpAfter, (_message, recipients) => recipients === accessEmail.recipients);
  const replacementOtp = otpFromEmail(replacementEmail.message);
  const verified = await request(`${erpBaseUrl}/api/supplier/${encodeURIComponent(magicToken)}/otp/verify`, {
    method: "POST",
    body: JSON.stringify({ otp: replacementOtp }),
  });
  if (verified.status !== 200 || !verified.cookie) throw new Error(`OTP verify failed for ${supplier} (${verified.status}): ${verified.raw}`);
  const supplierCookie = verified.cookie;
  const replay = await request(`${erpBaseUrl}/api/supplier/${encodeURIComponent(magicToken)}/otp/verify`, {
    method: "POST",
    body: JSON.stringify({ otp }),
  });
  if (replay.status === 200) throw new Error(`OTP replay was accepted for ${supplier}`);
  const summary = await request(`${erpBaseUrl}/api/supplier/session/process`, { headers: { Cookie: supplierCookie } });
  if (summary.status !== 200) throw new Error(`Supplier summary failed for ${supplier} (${summary.status}): ${summary.raw}`);
  const summaryRow = object(apiData(summary.body));
  const rfq = object(summaryRow.rfq as Json);
  const rfqItems = Array.isArray(rfq.items) ? rfq.items : [];
  if (!rfqItems.length) throw new Error(`Supplier ${supplier} has no RFQ items`);
  const quotation = await request(`${erpBaseUrl}/api/supplier/session/quotation`, {
    method: "POST",
    headers: { Cookie: supplierCookie },
    body: JSON.stringify({ items: rfqItems.map((item) => ({
      request_for_quotation_item: text(object(item as Json).name),
      qty: Number(object(item as Json).qty ?? 0),
      rate,
    })) }),
  });
  if (quotation.status !== 200) throw new Error(`Quotation submit failed for ${supplier} (${quotation.status}): ${quotation.raw}`);
  const quotationData = object(apiData(quotation.body));
  const result = object(quotationData.result as Json);
  const gate = object(quotationData.gate as Json);
  const quotationName = text(result.supplier_quotation || result.supplier_quotation_name || result.name || object(result.quotation as Json).name);
  if (!quotationName) throw new Error(`Quotation submit returned no quotation name for ${supplier}: ${quotation.raw}`);
  if (!/^SQ-\d{8}-\d{4}$/.test(quotationName)) throw new Error(`Supplier Quotation naming contract failed for ${supplier}: ${quotationName}`);
  const quotationSummary = await request(`${erpBaseUrl}/api/supplier/session/process`, { headers: { Cookie: supplierCookie } });
  if (quotationSummary.status !== 200) throw new Error(`Quotation readback failed for ${supplier} (${quotationSummary.status}): ${quotationSummary.raw}`);
  const quotationRow = object(object(apiData(quotationSummary.body)).quotation as Json);
  if (text(quotationRow.name) !== quotationName || text(quotationRow.status) !== "Submitted") {
    throw new Error(`Quotation was not submitted and locked for ${supplier}: ${quotationSummary.raw}`);
  }
  const duplicateQuotation = await request(`${erpBaseUrl}/api/supplier/session/quotation`, {
    method: "POST",
    headers: { Cookie: supplierCookie },
    body: JSON.stringify({ items: rfqItems.map((item) => ({
      request_for_quotation_item: text(object(item as Json).name),
      qty: Number(object(item as Json).qty ?? 0),
      rate,
    })) }),
  });
  const duplicateQuotationData = object(apiData(duplicateQuotation.body));
  const duplicateQuotationResult = object(duplicateQuotationData.result as Json);
  if (duplicateQuotation.status !== 200 || text(duplicateQuotationResult.supplier_quotation) !== quotationName || duplicateQuotationResult.idempotent !== true) {
    throw new Error(`Duplicate quotation submission was not idempotent for ${supplier}: ${duplicateQuotation.raw}`);
  }
  return { quotation: quotationName, gate, approval: object(quotationData.approval as Json), accessEmail: accessEmail.recipients, otpEmail: otpEmail.recipients, sessionCookie: supplierCookie, otpReplayRejected: true, otpLockRejections };
}

async function waitForPurchaseOrder(flow: { sessionCookie: string }, instanceCode: string, timeoutSeconds: number): Promise<Record<string, unknown>> {
  const deadline = Date.now() + timeoutSeconds * 1000;
  while (Date.now() < deadline) {
    await reconcileLarkApproval(instanceCode);
    const response = await request(`${erpBaseUrl}/api/supplier/session/process`, { headers: { Cookie: flow.sessionCookie } });
    if (response.status === 200) {
      const summary = object(apiData(response.body));
      const purchaseOrder = object(summary.purchase_order as Json);
      if (text(purchaseOrder.name)) return summary;
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 2000));
  }
  throw new Error(`PO was not created after approval within ${timeoutSeconds}s; ensure the Lark approval webhook is delivered`);
}

async function autoApproveLarkInstance(instanceCode: string): Promise<void> {
  const response = await request(`${authBaseUrl}/api/internal/lark/approval/approve`, {
    method: "POST",
    headers: { Authorization: `Bearer ${await env("LETRON_API_KEY")}` },
    body: JSON.stringify({ instance_code: instanceCode }),
  });
  if (response.status !== 200) throw new Error(`Lark approval auto-approve failed (${response.status}): ${response.raw}`);
  const result = object(apiData(response.body));
  if (!text(result.status)) throw new Error(`Lark approval auto-approve returned no status: ${response.raw}`);
}

async function reconcileLarkApproval(instanceCode: string): Promise<void> {
  const response = await request(`${authBaseUrl}/api/internal/lark/approval/reconcile`, {
    method: "POST",
    headers: { Authorization: `Bearer ${await env("LETRON_API_KEY")}` },
    body: JSON.stringify({ instance_code: instanceCode }),
  });
  if (response.status !== 200) throw new Error(`Lark approval reconcile failed (${response.status}): ${response.raw}`);
}

async function reviewSubmission(authCookie: string, submission: string): Promise<Record<string, unknown>> {
  const response = await request(`${erpBaseUrl}/api/internal/supplier-portal/review`, {
    method: "POST",
    headers: { Cookie: authCookie },
    body: JSON.stringify({ submission, decision: "Approved", review_note: "real-test approved" }),
  });
  if (response.status !== 200) throw new Error(`Internal review failed (${response.status}): ${response.raw}`);
  return object(apiData(response.body));
}

async function ensureSupplier(auth: { Cookie: string }, supplier: string): Promise<void> {
  const listed = await request(`${erpBaseUrl}/api/purchase/suppliers?limit_page_length=100`, { headers: auth });
  if (listed.status !== 200) throw new Error(`supplier preflight failed (${listed.status}): ${listed.raw}`);
  const rows = apiData(listed.body);
  const exists = Array.isArray(rows) && rows.some((row) => {
    const item = object(row as Json);
    return text(item.name) === supplier || text(item.supplier_name) === supplier;
  });
  if (exists) return;
  const created = await request(`${erpBaseUrl}/api/purchase/suppliers`, {
    method: "POST",
    headers: auth,
    body: JSON.stringify({ supplier_name: supplier, supplier_group: "All Supplier Groups", supplier_type: "Company" }),
  });
  if (created.status < 200 || created.status >= 300) throw new Error(`supplier creation failed (${created.status}): ${created.raw}`);
}

async function ensureTestItem(auth: { Cookie: string }): Promise<void> {
  if (item2) return;
  const source = await request(`${erpBaseUrl}/api/purchase/items/${encodeURIComponent(item1)}`, { headers: auth });
  if (source.status !== 200) throw new Error(`test item source read failed (${source.status}): ${source.raw}`);
  const sourceRow = object(apiData(source.body));
  const marker = Date.now().toString(16).slice(-8).padStart(8, "0");
  item2 = `ACCEPTANCE-LOCAL-${marker}-Purchase Flow Item`;
  const created = await request(`${erpBaseUrl}/api/purchase/items`, {
    method: "POST",
    headers: auth,
    body: JSON.stringify({
      item_code: item2,
      item_name: item2,
      item_group: text(sourceRow.item_group),
      stock_uom: text(sourceRow.stock_uom) || "Nos",
      is_stock_item: 1,
      valuation_rate: 1000,
    }),
  });
  if (created.status < 200 || created.status >= 300) throw new Error(`test item creation failed (${created.status}): ${created.raw}`);
}

async function main(): Promise<void> {
const suppliers = [supplier1, ...(supplier2 && supplier2 !== supplier1 ? [supplier2] : [])];
const apiKey = await env("LETRON_API_KEY");
const apiAuth = { Authorization: `Bearer ${apiKey}` };

const session = await request(`${portalBaseUrl}/api/internal/test-session`, {
  method: "POST",
  headers: apiAuth,
});
if (session.status !== 200) throw new Error(`test-session failed (${session.status}): ${session.raw}`);
if (!session.cookie) throw new Error("test-session did not return a session cookie");
const auth = { Cookie: session.cookie };

for (const supplier of suppliers) await ensureSupplier(auth, supplier);
await ensureTestItem(auth);

const seedList = await request(`${erpBaseUrl}/api/purchase/material-requests?limit_page_length=1&order_by=creation%20desc`, { headers: auth });
if (seedList.status !== 200) throw new Error(`cannot read seed MR (${seedList.status}): ${seedList.raw}`);
const seedValue = apiData(seedList.body);
const seed = object(Array.isArray(seedValue) ? (seedValue[0] as Json) : seedValue);
const seedName = text(seed.name);
if (!seedName) throw new Error("no existing Material Request available");

const seedDetail = await request(`${erpBaseUrl}/api/purchase/material-requests/${encodeURIComponent(seedName)}`, { headers: auth });
if (seedDetail.status !== 200) throw new Error(`cannot read seed MR ${seedName} (${seedDetail.status}): ${seedDetail.raw}`);
const seedRow = object(apiData(seedDetail.body));
const company = text(seedRow.company);
const items = Array.isArray(seedRow.items) ? seedRow.items : [];
const warehouse = text(items.map((row) => object(row as Json).warehouse).find(Boolean));
if (!company || !warehouse) throw new Error(`seed MR ${seedName} has no usable company/warehouse`);

const today = new Date();
const emailAfter = new Date(today.getTime() - 2_000).toISOString();
const transactionDate = today.toISOString().slice(0, 10);
today.setUTCDate(today.getUTCDate() + 30);
const scheduleDate = today.toISOString().slice(0, 10);
const payload = {
  material_request: {
    material_request_type: "Purchase",
    company,
    transaction_date: transactionDate,
    schedule_date: scheduleDate,
    title: "Real MR approval integration test",
    items: [
      { item_code: item1, qty: 2, warehouse, schedule_date: scheduleDate, rate: 1000 },
      { item_code: item2, qty: 3, warehouse, schedule_date: scheduleDate, rate: 2000 },
    ],
  },
  suppliers,
  supplier_email: supplierEmail,
  justification: "Real MR to Lark Approval integration test",
};

const created = await request(`${erpBaseUrl}/api/purchase/requests/create`, {
  method: "POST",
  headers: { ...auth, "X-Idempotency-Key": idempotencyKey },
  body: JSON.stringify(payload),
});
if (created.status < 200 || created.status >= 300) {
  throw new Error(`real MR orchestration failed (${created.status}): ${created.raw}`);
}
const result = object(apiData(created.body));
const mrName = text(result.material_request_name);
const rfqName = text(result.request_for_quotation_name);
if (!mrName || !rfqName) throw new Error(`orchestration did not return MR and RFQ: ${created.raw}`);
if (!/^MR-\d{8}-\d{4}$/.test(mrName)) throw new Error(`Material Request naming contract failed: ${mrName}`);
if (!/^RFQ-\d{8}-\d{4}$/.test(rfqName)) throw new Error(`Request for Quotation naming contract failed: ${rfqName}`);
if (text(result.status) !== "waiting_supplier_quotes") {
  throw new Error(`orchestration did not stop at supplier quotation gate: ${created.raw}`);
}

const readback = await request(`${erpBaseUrl}/api/purchase/material-requests/${encodeURIComponent(mrName)}`, { headers: auth });
if (readback.status !== 200) throw new Error(`MR readback failed (${readback.status}): ${readback.raw}`);
const createdRow = object(apiData(readback.body));
const itemCount = Array.isArray(createdRow.items) ? createdRow.items.length : 0;
if (itemCount !== 2) throw new Error(`MR ${mrName} has ${itemCount} items; expected 2`);

const usedTokens = new Set<string>();
const supplierResults = [];
for (let index = 0; index < suppliers.length; index += 1) {
  supplierResults.push(await supplierFlow(suppliers[index], emailAfter, index === 0 ? 1000 : 900, usedTokens));
}
const gate = supplierResults[supplierResults.length - 1].gate;
const cheapestResult = supplier2 ? supplierResults[1] : supplierResults[0];
if (text(gate.selected_supplier_quotation) !== cheapestResult.quotation) {
  throw new Error(`cheapest quotation was not selected: ${JSON.stringify(gate)}`);
}
const approval = cheapestResult.approval;
const approvalInstance = text(approval.instanceCode || approval.instance_code);
if (!approvalInstance) throw new Error("Lark approval was not opened after the final supplier quotation");
const poDraftName = text(approval.erpPurchaseOrderName || approval.erp_purchase_order_name || approval.purchase_order);
if (!/^PO-\d{8}-\d{4}$/.test(poDraftName)) {
  throw new Error(`Approval did not return a native ERPNext PO number: ${JSON.stringify(approval)}`);
}
const poDraftReadback = await request(`${erpBaseUrl}/api/purchase/purchase-orders/${encodeURIComponent(poDraftName)}`, { headers: auth });
if (poDraftReadback.status !== 200) throw new Error(`PO Draft readback failed (${poDraftReadback.status}): ${poDraftReadback.raw}`);
const poDraftRow = object(apiData(poDraftReadback.body));
if (text(poDraftRow.name) !== poDraftName || Number(poDraftRow.docstatus ?? -1) !== 0) {
  throw new Error(`ERPNext PO was not Draft before approval: ${poDraftReadback.raw}`);
}

const winningFlow = cheapestResult;
await autoApproveLarkInstance(approvalInstance);
const summaryWithPo = await waitForPurchaseOrder(winningFlow, approvalInstance, Number(process.env.MR_APPROVAL_WAIT_SECONDS ?? 300));
const purchaseOrder = object(summaryWithPo.purchase_order as Json);
const poName = text(purchaseOrder.name);
const poItems = Array.isArray(purchaseOrder.items) ? purchaseOrder.items : [];
if (!poName || !poItems.length || text(purchaseOrder.status) !== "Submitted") throw new Error(`PO is not submitted: ${JSON.stringify(purchaseOrder)}`);
if (poName !== poDraftName) throw new Error(`Approval created a different PO: draft=${poDraftName}, submitted=${poName}`);

const deliveryPayload = {
  delivery_date: transactionDate,
  idempotency_key: `${idempotencyKey}:delivery`,
  items: poItems.map((item) => ({ purchase_order_item: text(object(item as Json).name), delivered_qty: Number(object(item as Json).qty ?? 0), uom: text(object(item as Json).uom) })),
};
const delivery = await request(`${erpBaseUrl}/api/supplier/session/delivery`, {
  method: "POST",
  headers: { Cookie: winningFlow.sessionCookie },
  body: JSON.stringify(deliveryPayload),
});
if (delivery.status !== 201) throw new Error(`Delivery submission failed (${delivery.status}): ${delivery.raw}`);
const deliverySubmission = text(object(apiData(delivery.body)).submission);
if (!deliverySubmission) throw new Error(`Delivery submission id missing: ${delivery.raw}`);
const duplicateDelivery = await request(`${erpBaseUrl}/api/supplier/session/delivery`, {
  method: "POST",
  headers: { Cookie: winningFlow.sessionCookie },
  body: JSON.stringify(deliveryPayload),
});
if (duplicateDelivery.status !== 201 || text(object(apiData(duplicateDelivery.body)).submission) !== deliverySubmission) {
  throw new Error(`Duplicate delivery submission was not idempotent: ${duplicateDelivery.raw}`);
}
const deliveryReview = await reviewSubmission(session.cookie, deliverySubmission);
const receiptName = text(deliveryReview.result_document);
if (!receiptName) throw new Error(`Purchase Receipt was not created: ${JSON.stringify(deliveryReview)}`);
if (!/^GRN-\d{8}-\d{4}$/.test(receiptName)) throw new Error(`Purchase Receipt naming contract failed: ${receiptName}`);

const xml = new FormData();
xml.set("file", new Blob(["<?xml version=\"1.0\" encoding=\"UTF-8\"?><Invoice><InvoiceNumber>REAL-TEST</InvoiceNumber></Invoice>"], { type: "application/xml" }), "real-test.xml");
xml.set("invoice_number", `REAL-${Date.now()}`);
xml.set("invoice_date", transactionDate);
xml.set("invoice_total", String(Number(purchaseOrder.grand_total ?? 0)));
xml.set("idempotency_key", `${idempotencyKey}:invoice`);
const invoice = await request(`${erpBaseUrl}/api/supplier/session/xml-invoice`, { method: "POST", headers: { Cookie: winningFlow.sessionCookie }, body: xml });
if (invoice.status !== 201) throw new Error(`XML invoice upload failed (${invoice.status}): ${invoice.raw}`);
const invoiceSubmission = text(object(apiData(invoice.body)).submission);
if (!invoiceSubmission) throw new Error(`XML invoice submission id missing: ${invoice.raw}`);
const duplicateXml = new FormData();
duplicateXml.set("file", new Blob(["<?xml version=\"1.0\" encoding=\"UTF-8\"?><Invoice><InvoiceNumber>REAL-TEST</InvoiceNumber></Invoice>"], { type: "application/xml" }), "real-test.xml");
duplicateXml.set("invoice_number", text(xml.get("invoice_number")));
duplicateXml.set("invoice_date", transactionDate);
duplicateXml.set("invoice_total", String(Number(purchaseOrder.grand_total ?? 0)));
duplicateXml.set("idempotency_key", `${idempotencyKey}:invoice`);
const duplicateInvoice = await request(`${erpBaseUrl}/api/supplier/session/xml-invoice`, { method: "POST", headers: { Cookie: winningFlow.sessionCookie }, body: duplicateXml });
if (duplicateInvoice.status !== 201 || text(object(apiData(duplicateInvoice.body)).submission) !== invoiceSubmission) {
  throw new Error(`Duplicate XML submission was not idempotent: ${duplicateInvoice.raw}`);
}
const invoiceReview = await reviewSubmission(session.cookie, invoiceSubmission);
const invoiceName = text(invoiceReview.result_document);
if (!invoiceName) throw new Error(`Purchase Invoice was not created: ${JSON.stringify(invoiceReview)}`);
if (!/^INV-\d{8}-\d{4}$/.test(invoiceName)) throw new Error(`Purchase Invoice naming contract failed: ${invoiceName}`);
const finalSummary = await request(`${erpBaseUrl}/api/supplier/session/process`, { headers: { Cookie: winningFlow.sessionCookie } });
if (finalSummary.status !== 200) throw new Error(`Final process readback failed (${finalSummary.status}): ${finalSummary.raw}`);
const finalRow = object(apiData(finalSummary.body));
const finalReceipt = object(finalRow.purchase_receipt as Json);
const finalInvoice = object(finalRow.purchase_invoice as Json);
if (text(finalReceipt.name) !== receiptName || text(finalReceipt.status) !== "Submitted") throw new Error(`Purchase Receipt was not submitted: ${finalSummary.raw}`);
if (text(finalInvoice.name) !== invoiceName || text(finalInvoice.status) !== "Submitted") throw new Error(`Purchase Invoice was not submitted: ${finalSummary.raw}`);
const overflowPayload = {
  delivery_date: transactionDate,
  idempotency_key: `${idempotencyKey}:quantity-overflow`,
  items: poItems.map((item, index) => ({ purchase_order_item: text(object(item as Json).name), delivered_qty: index === 0 ? Number(object(item as Json).qty ?? 0) + 1 : 0, uom: text(object(item as Json).uom) })),
};
const overflow = await request(`${erpBaseUrl}/api/supplier/session/delivery`, {
  method: "POST",
  headers: { Cookie: winningFlow.sessionCookie },
  body: JSON.stringify(overflowPayload),
});
if (overflow.status < 400 || overflow.status >= 500) throw new Error(`Quantity overflow was accepted or returned a server error: ${overflow.raw}`);
const payment = await request(`${erpBaseUrl}/api/supplier/session/payment-status`, { headers: { Cookie: winningFlow.sessionCookie } });
if (payment.status !== 200) throw new Error(`Payment status readback failed (${payment.status}): ${payment.raw}`);
const paymentData = object(apiData(payment.body));
if (text(paymentData.payment_status) !== "Invoiced") throw new Error(`Unexpected payment status: ${payment.raw}`);

console.log("REAL_MR_TEST=PASS");
console.log(`status=${text(result.status)}`);
console.log(`orchestration_id=${text(result.id)}`);
console.log(`material_request=${mrName}`);
console.log(`request_for_quotation=${rfqName}`);
console.log(`approval_instance=${approvalInstance}`);
console.log(`items=${itemCount}`);
console.log(`suppliers=${Array.isArray(result.suppliers) ? result.suppliers.length : 0}`);
console.log(`supplier_magic_otp_flows=${supplierResults.length}`);
console.log(`otp_resend_rate_limit_checks=${supplierResults.length}`);
console.log(`otp_replay_rejections=${supplierResults.filter((item) => item.otpReplayRejected).length}`);
console.log(`otp_lock_rejections=${supplierResults.reduce((total, item) => total + item.otpLockRejections, 0)}`);
console.log(`selected_cheapest_quotation=${text(gate.selected_supplier_quotation)}`);
console.log(`supplier_email_readback=${supplierResults.map((item) => item.accessEmail).join(",")}`);
console.log(`purchase_order=${poName}`);
console.log(`purchase_receipt=${receiptName}`);
console.log(`purchase_invoice=${invoiceName}`);
console.log(`payment_status=${text(paymentData.payment_status)}`);
console.log("quantity_overflow_rejections=1");
console.log("approver=leducanh@ledb.vn");
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
