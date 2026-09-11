import "server-only";

import { createHash, randomUUID, timingSafeEqual } from "node:crypto";
import { Redis } from "@upstash/redis";

import { ApiRequestError } from "./api-error";
import { frappeDocumentAction, frappeGet, frappeList, frappeUpdate } from "./frappe-client";
import { LARK_PO_APPROVAL_DESIGN } from "./lark-po-approval-design";
import { LARK_DOMAIN, LARK_PO_APPROVAL_CODE, LARK_PO_APPROVER_EMAIL } from "./lark-runtime-config";
import { supplierPortalConfig } from "./supplier-portal-config";
import { supplierQuotationRfqName } from "./supplier-portal-core";

type LarkEnvelope<T> = { data?: T; code?: number; msg?: string };
type Scalar = string | number | boolean | null | undefined;
type LarkFormOption = { key: string; value: string; text: string };
type LarkFieldListOption = { input_type?: string; print_type?: string; inputType?: string; printType?: string };
type LarkFormEntry = { id: string; type: string; value: string | LarkFormRow[] };
type LarkFormRow = LarkFormEntry[];
type LarkFormField = {
  id: string;
  custom_id?: string;
  name: string;
  type: string;
  value?: string | LarkFormOption[] | LarkFormField[];
  option?: LarkFormOption[] | LarkFieldListOption | null;
  children?: LarkFormField[];
};
type LarkApprovalCreateResult = { instance_code: string };
type LarkTenantTokenResponse = { tenant_access_token: string; expire: number };
type ErpSubmittedDocument = { name?: string; docstatus?: number };

type ErpBaseDocument = {
  name: string;
  docstatus: number;
  custom_letron_orchestration_id?: string | null;
};

type SupplierQuotationItem = {
  name: string;
  item_code: string;
  item_name: string;
  description?: string | null;
  qty: number;
  uom: string;
  rate: number;
  amount: number;
  warehouse: string;
  material_request: string;
  material_request_item: string;
  request_for_quotation: string;
  request_for_quotation_item: string;
};

type SupplierQuotation = ErpBaseDocument & {
  supplier: string;
  company: string;
  currency?: string | null;
  terms?: string | null;
  incoterm?: string | null;
  net_total: number;
  total_taxes_and_charges: number;
  grand_total: number;
  items: SupplierQuotationItem[];
};

type PurchaseOrderItem = {
  name: string;
  item_code: string;
  uom: string;
  qty: number;
  rate: number;
  amount?: number;
  warehouse?: string | null;
};

type PurchaseOrder = ErpBaseDocument & {
  supplier: string;
  company: string;
  transaction_date: string;
  schedule_date: string;
  currency: string;
  conversion_rate: number;
  custom_lark_approval_instance_code?: string | null;
  items: PurchaseOrderItem[];
};

type MaterialRequest = ErpBaseDocument & { items?: Array<Record<string, unknown>> };
type RequestForQuotation = ErpBaseDocument & { status?: string | null; items?: Array<Record<string, unknown>> };

type LarkApprovalDefinition = {
  form: string;
  node_list: Array<{ node_id: string; name?: string; need_approver: boolean }>;
};
type LarkApprovalTask = { id: string; status: string; user_id: string };
type LarkApprovalInstance = { status: string; task_list?: LarkApprovalTask[] };
type ApprovalInstanceMapping = {
  purchase_order: string;
  supplier_quotation: string;
  material_request: string;
  request_for_quotation: string;
  source_fingerprint: string;
};

type ApprovalItem = {
  item_code: string;
  item_name: string;
  description: string;
  qty: number;
  uom: string;
  rate: number;
  amount: number;
  warehouse: string;
  material_request: string;
  material_request_item: string;
  request_for_quotation: string;
  request_for_quotation_item: string;
  supplier_quotation: string;
  supplier_quotation_item: string;
};

type ApprovalSource = {
  orchestrationId: string;
  materialRequestName: string;
  rfqName: string;
  quotationName: string;
  purchaseOrderName: string;
  supplier: string;
  company: string;
  transactionDate: string;
  scheduleDate: string;
  currency: string;
  conversionRate: number;
  netTotal: number;
  totalTaxes: number;
  grandTotal: number;
  paymentTerms: string;
  deliveryTerms: string;
  justification: string;
  items: ApprovalItem[];
  existingInstanceCode: string;
  sourceFingerprint: string;
};

let redis: Redis | undefined;

function stringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : String(value ?? "").trim();
}

function numericValue(value: Scalar, label: string): number {
  const result = Number(value);
  if (!Number.isFinite(result)) {
    throw new ApiRequestError("approval_source_invalid", `${label} is missing or invalid.`, 409);
  }
  return result;
}

function config(): { approvalCode: string; domain: string; appId: string; appSecret: string } {
  const result = {
    approvalCode: LARK_PO_APPROVAL_CODE,
    domain: LARK_DOMAIN,
    appId: stringValue(process.env.LARK_APP_ID),
    appSecret: stringValue(process.env.LARK_APP_SECRET),
  };
  if (!result.approvalCode || !result.domain || !result.appId || !result.appSecret) {
    throw new ApiRequestError("configuration_error", "Lark Approval is not configured.", 503);
  }
  return result;
}

function database(): Redis {
  if (redis) return redis;
  const url = stringValue(process.env.KV_REST_API_URL);
  const token = stringValue(process.env.KV_REST_API_TOKEN);
  if (!url || !token) {
    throw new ApiRequestError("configuration_error", "Lark Approval storage is not configured.", 503);
  }
  redis = new Redis({ url, token });
  return redis;
}

function instanceKey(instanceCode: string): string {
  return `erp:lark-approval:instance:${instanceCode}`;
}

async function lock<T>(name: string, callback: () => Promise<T>): Promise<T> {
  const key = `erp:lark-approval:lock:${createHash("sha256").update(name).digest("hex")}`;
  const owner = randomUUID();
  if (!(await database().set(key, owner, { nx: true, ex: 180 }))) {
    throw new ApiRequestError("lark_approval_in_progress", "Approval is already being processed.", 409, true, 2);
  }
  try {
    return await callback();
  } finally {
    await database()
      .eval(
        "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
        [key],
        [owner],
      )
      .catch(() => undefined);
  }
}

async function tenantToken(): Promise<string> {
  const env = config();
  const key = "erp:lark-approval:tenant-token";
  const cached = await database().get<{ token: string; expires_at: number }>(key);
  if (cached && cached.expires_at > Date.now() + 30_000) return cached.token;

  return lock("tenant-token", async () => {
    const current = await database().get<{ token: string; expires_at: number }>(key);
    if (current && current.expires_at > Date.now() + 30_000) return current.token;
    const response = await fetch(new URL("/open-apis/auth/v3/tenant_access_token/internal", env.domain), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ app_id: env.appId, app_secret: env.appSecret }),
      signal: AbortSignal.timeout(10_000),
    });
    const payload = (await response.json().catch(() => null)) as LarkTenantTokenResponse | null;
    const token = stringValue(payload?.tenant_access_token);
    const expires = Math.max(60, Number(payload?.expire) || 60);
    if (!response.ok || !token) throw new Error("LARK_TENANT_TOKEN_FAILED");
    await database().set(key, { token, expires_at: Date.now() + expires * 1000 }, { ex: expires });
    return token;
  });
}

async function lark<T>(path: string, init: RequestInit = {}): Promise<T> {
  const env = config();
  const response = await fetch(new URL(path, env.domain), {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      authorization: `Bearer ${await tenantToken()}`,
      ...(init.headers ?? {}),
    },
    cache: "no-store",
    signal: init.signal ?? AbortSignal.timeout(30_000),
  });
  const payload = (await response.json().catch(() => null)) as LarkEnvelope<T> | null;
  if (!response.ok || (typeof payload?.code === "number" && payload.code !== 0)) {
    console.error(`[lark-approval] request_failed status=${response.status} code=${payload?.code ?? ""} detail=${stringValue(payload?.msg).slice(0, 200)}`);
    throw new Error(`LARK_REQUEST_FAILED_${response.status || payload?.code || "UNKNOWN"}`);
  }
  if (!payload || payload.data === undefined) throw new Error("LARK_RESPONSE_DATA_MISSING");
  return payload.data;
}

async function userId(email: string): Promise<string> {
  const result = await lark<{ user_list?: Array<{ user_id?: string }> }>(
    "/open-apis/contact/v3/users/batch_get_id?user_id_type=user_id",
    { method: "POST", body: JSON.stringify({ emails: [email] }) },
  );
  if (!Array.isArray(result.user_list) || result.user_list.length !== 1) throw new Error("LARK_USER_ID_NOT_UNIQUE");
  const id = stringValue(result.user_list[0]?.user_id);
  if (!id) throw new Error("LARK_USER_ID_NOT_FOUND");
  return id;
}

function quotationItem(item: SupplierQuotationItem, quotationName: string): ApprovalItem {
  return {
    item_code: stringValue(item.item_code),
    item_name: stringValue(item.item_name),
    description: stringValue(item.description),
    qty: numericValue(item.qty, "quotation quantity"),
    uom: stringValue(item.uom),
    rate: numericValue(item.rate, "quotation rate"),
    amount: numericValue(item.amount, "quotation amount"),
    warehouse: stringValue(item.warehouse),
    material_request: stringValue(item.material_request),
    material_request_item: stringValue(item.material_request_item),
    request_for_quotation: stringValue(item.request_for_quotation),
    request_for_quotation_item: stringValue(item.request_for_quotation_item),
    supplier_quotation: quotationName,
    supplier_quotation_item: stringValue(item.name),
  };
}

function sourceFingerprint(source: {
  quotation: SupplierQuotation;
  purchaseOrder: PurchaseOrder;
  items: ApprovalItem[];
}): string {
  return createHash("sha256")
    .update(
      JSON.stringify({
        quotation: {
          name: source.quotation.name,
          docstatus: source.quotation.docstatus,
          supplier: source.quotation.supplier,
          company: source.quotation.company,
          currency: source.quotation.currency,
          net_total: source.quotation.net_total,
          total_taxes_and_charges: source.quotation.total_taxes_and_charges,
          grand_total: source.quotation.grand_total,
        },
        purchaseOrder: {
          name: source.purchaseOrder.name,
          docstatus: source.purchaseOrder.docstatus,
          supplier: source.purchaseOrder.supplier,
          company: source.purchaseOrder.company,
          transaction_date: source.purchaseOrder.transaction_date,
          schedule_date: source.purchaseOrder.schedule_date,
          currency: source.purchaseOrder.currency,
          conversion_rate: source.purchaseOrder.conversion_rate,
        },
        items: source.items,
      }),
    )
    .digest("hex");
}

async function approvalSource(input: {
  orchestrationId: string;
  supplierQuotationName: string;
  erpPurchaseOrderName: string;
  materialRequestName?: string;
  rfqName?: string;
  justification?: string;
}): Promise<ApprovalSource> {
  const [quotation, purchaseOrder] = await Promise.all([
    frappeGet<SupplierQuotation>("Supplier Quotation", input.supplierQuotationName),
    frappeGet<PurchaseOrder>("Purchase Order", input.erpPurchaseOrderName),
  ]);
  const rawItems = quotation.items;
  const [materialRequestRows, rfqRows] = await Promise.all([
    frappeList<MaterialRequest>(
      "Material Request",
      [["custom_letron_orchestration_id", "=", input.orchestrationId]],
      ["name", "custom_letron_orchestration_id"],
      2,
    ),
    frappeList<RequestForQuotation>(
      "Request for Quotation",
      [["custom_letron_orchestration_id", "=", input.orchestrationId]],
      ["name", "custom_letron_orchestration_id"],
      2,
    ),
  ]);
  const rfqName = input.rfqName || supplierQuotationRfqName(quotation) || stringValue(rfqRows[0]?.name);
  const materialRequests = new Set(rawItems.map((item) => stringValue(item.material_request)).filter(Boolean));
  const mrName = input.materialRequestName || (materialRequests.size === 1
    ? [...materialRequests][0]
    : stringValue(materialRequestRows[0]?.name));
  if (!mrName || !rfqName) throw new ApiRequestError("approval_source_missing", "Purchase source documents are missing.", 409);

  const [materialRequest, rfq] = await Promise.all([
    frappeGet<MaterialRequest>("Material Request", mrName),
    frappeGet<RequestForQuotation>("Request for Quotation", rfqName),
  ]);
  for (const [label, document] of [
    ["material_request", materialRequest],
    ["request_for_quotation", rfq],
    ["supplier_quotation", quotation],
    ["purchase_order", purchaseOrder],
  ] as const) {
    if (stringValue(document.custom_letron_orchestration_id) !== input.orchestrationId) {
      throw new ApiRequestError(
        "approval_source_mismatch",
        `Approval source ${label} (${document.name}) does not belong to this orchestration.`,
        409,
      );
    }
  }
  if (Number(quotation.docstatus) !== 1 || Number(purchaseOrder.docstatus) !== 0) {
    throw new ApiRequestError("approval_source_status_invalid", "Approval source status is invalid.", 409);
  }
  if (
    !stringValue(purchaseOrder.supplier) ||
    stringValue(purchaseOrder.supplier) !== stringValue(quotation.supplier) ||
    !stringValue(purchaseOrder.company) ||
    stringValue(purchaseOrder.company) !== stringValue(quotation.company)
  ) {
    throw new ApiRequestError("approval_source_mismatch", "Purchase sources do not match.", 409);
  }
  if (!rawItems.length) throw new ApiRequestError("approval_items_missing", "Supplier quotation has no items.", 409);

  const rfqItems = rfq.items ?? [];
  const mrItems = materialRequest.items ?? [];
  const items = rawItems.map((item) => {
    const rfqItem = rfqItems.find((candidate) => stringValue(candidate.item_code) === stringValue(item.item_code));
    const mrItem = mrItems.find((candidate) => stringValue(candidate.item_code) === stringValue(item.item_code));
    return quotationItem({
      ...item,
      item_name: stringValue(item.item_name) || stringValue(rfqItem?.item_name) || stringValue(mrItem?.item_name),
      uom: stringValue(item.uom) || stringValue(rfqItem?.uom) || stringValue(mrItem?.uom),
      warehouse: stringValue(item.warehouse) || stringValue(rfqItem?.warehouse) || stringValue(mrItem?.warehouse),
      material_request: stringValue(item.material_request) || mrName,
      material_request_item: stringValue(item.material_request_item) || stringValue(mrItem?.name),
      request_for_quotation: stringValue(item.request_for_quotation) || rfq.name,
      request_for_quotation_item: stringValue(item.request_for_quotation_item) || stringValue(rfqItem?.name),
    }, quotation.name);
  });
  if (
    items.some(
      (item) =>
        !item.item_code ||
        !item.item_name ||
        !item.uom ||
        !item.warehouse ||
        !item.material_request ||
        !item.material_request_item ||
        !item.request_for_quotation ||
        !item.request_for_quotation_item ||
        item.qty <= 0 ||
        item.rate < 0 ||
        item.amount < 0,
    )
  ) {
    throw new ApiRequestError("approval_item_invalid", "Supplier quotation item is invalid.", 409);
  }

  const transactionDate = stringValue(purchaseOrder.transaction_date);
  const scheduleDate = stringValue(purchaseOrder.schedule_date);
  const currency = stringValue(purchaseOrder.currency);
  const justification = stringValue(input.justification);
  if (!transactionDate || !scheduleDate || !currency || !justification) {
    throw new ApiRequestError("approval_source_invalid", "Approval source contains missing required fields.", 409);
  }

  return {
    orchestrationId: input.orchestrationId,
    materialRequestName: stringValue(materialRequest.name),
    rfqName: stringValue(rfq.name),
    quotationName: stringValue(quotation.name),
    purchaseOrderName: stringValue(purchaseOrder.name),
    supplier: stringValue(purchaseOrder.supplier),
    company: stringValue(purchaseOrder.company),
    transactionDate,
    scheduleDate,
    currency,
    conversionRate: numericValue(purchaseOrder.conversion_rate, "conversion rate"),
    netTotal: numericValue(quotation.net_total, "net total"),
    totalTaxes: numericValue(quotation.total_taxes_and_charges, "total taxes"),
    grandTotal: numericValue(quotation.grand_total, "grand total"),
    paymentTerms: stringValue(quotation.terms),
    deliveryTerms: stringValue(quotation.incoterm),
    justification,
    items,
    existingInstanceCode: stringValue(purchaseOrder.custom_lark_approval_instance_code),
    sourceFingerprint: sourceFingerprint({ quotation, purchaseOrder, items }),
  };
}

function liveForm(value: string): LarkFormField[] {
  const result = JSON.parse(value) as LarkFormField[];
  if (!Array.isArray(result)) throw new Error("LARK_APPROVAL_FORM_INVALID");
  return result;
}

function requiredArray<T>(value: T[] | undefined, error: string): T[] {
  if (!Array.isArray(value) || value.length === 0) throw new Error(error);
  return value;
}

function fieldByKey(fields: LarkFormField[], key: string): LarkFormField {
  const expected = LARK_PO_APPROVAL_DESIGN.fields.find((field) => field.key === key);
  const matches = expected ? fields.filter((field) => field.name === expected.label && field.type === expected.type) : [];
  if (!expected || matches.length !== 1) {
    throw new Error(`LARK_APPROVAL_FIELD_INVALID_${key}`);
  }
  return matches[0];
}

function columnByKey(children: LarkFormField[], key: string): LarkFormField {
  const expected = LARK_PO_APPROVAL_DESIGN.table.columns.find((column) => column.key === key);
  const matches = expected ? children.filter((field) => field.name === expected.label && field.type === "input") : [];
  if (!expected || matches.length !== 1) {
    throw new Error(`LARK_APPROVAL_COLUMN_INVALID_${key}`);
  }
  return matches[0];
}

function formValue(field: LarkFormField): { id: string; type: string } {
  const id = stringValue(field.id);
  const type = stringValue(field.type);
  if (!id || !type) throw new Error("LARK_APPROVAL_FORM_FIELD_METADATA_MISSING");
  return { id, type };
}

function approvalForm(definition: string, source: ApprovalSource): LarkFormEntry[] {
  const fields = liveForm(definition);
  const reason = formValue(fieldByKey(fields, "reason"));
  const reference = formValue(fieldByKey(fields, "reference"));
  const purchaseTypeField = fieldByKey(fields, "purchaseType");
  const purchaseType = formValue(purchaseTypeField);
  const deliveryDate = formValue(fieldByKey(fields, "deliveryDate"));
  const detailsField = fieldByKey(fields, "details");
  const paymentTerms = formValue(fieldByKey(fields, "paymentTerms"));
  const deliveryTerms = formValue(fieldByKey(fields, "deliveryTerms"));
  const children = requiredArray(detailsField.children, "LARK_APPROVAL_COLUMNS_MISSING");
  const layout = detailsField.option;
  if (!layout || Array.isArray(layout) || (layout.input_type ?? layout.inputType) !== LARK_PO_APPROVAL_DESIGN.table.inputType || (layout.print_type ?? layout.printType) !== LARK_PO_APPROVAL_DESIGN.table.printType) {
    throw new Error("LARK_APPROVAL_TABLE_LAYOUT_INVALID");
  }
  const summary = formValue(columnByKey(children, "itemSummary"));
  const supplierRfq = formValue(columnByKey(children, "supplierRfq"));
  const quantity = formValue(columnByKey(children, "quantity"));
  const unitPrice = formValue(columnByKey(children, "unitPrice"));
  const lineTotal = formValue(columnByKey(children, "lineTotal"));
  const configuredType = LARK_PO_APPROVAL_DESIGN.fields.find((field) => field.key === "purchaseType");
  const options = requiredArray(Array.isArray(purchaseTypeField.option) ? purchaseTypeField.option : undefined, "LARK_APPROVAL_OPTIONS_MISSING");
  const selected = options.find((option) => option.text === configuredType?.selected);
  if (!selected) throw new Error("LARK_APPROVAL_PURCHASE_TYPE_NOT_CONFIGURED");

  const portalUrl = supplierPortalConfig().portal_public_base_url.replace(/\/$/, "");
  const referenceUrl = `${portalUrl}/purchase/requests?orchestration=${encodeURIComponent(source.orchestrationId)}`;
  const referenceText = [
    referenceUrl,
    `PO: ${source.purchaseOrderName}`,
    `MR: ${source.materialRequestName}`,
    `RFQ: ${source.rfqName}`,
    `Quotation: ${source.quotationName}`,
    `Orchestration: ${source.orchestrationId}`,
  ].join("\n");
  const rows = source.items.map((item) => [
    { id: summary.id, type: "input", value: `${item.item_name}${item.description ? ` | ${item.description}` : ""}` },
    { id: supplierRfq.id, type: "input", value: `${source.supplier} | RFQ: ${source.rfqName}` },
    { id: quantity.id, type: "input", value: String(item.qty) },
    { id: unitPrice.id, type: "input", value: `${item.rate.toLocaleString("en-US")} ${source.currency}` },
    { id: lineTotal.id, type: "input", value: `${item.amount.toLocaleString("en-US")} ${source.currency}` },
  ]);
  rows.push([
    { id: summary.id, type: "input", value: "TỔNG CỘNG" },
    { id: supplierRfq.id, type: "input", value: "—" },
    { id: quantity.id, type: "input", value: "—" },
    { id: unitPrice.id, type: "input", value: "—" },
    { id: lineTotal.id, type: "input", value: `${source.grandTotal.toLocaleString("en-US")} ${source.currency}` },
  ]);

  return [
    { id: reason.id, type: reason.type, value: source.justification },
    { id: reference.id, type: reference.type, value: referenceText },
    { id: purchaseType.id, type: purchaseType.type, value: stringValue(selected.value) },
    { id: deliveryDate.id, type: deliveryDate.type, value: `${source.scheduleDate}T00:00:00+07:00` },
    { id: paymentTerms.id, type: paymentTerms.type, value: source.paymentTerms },
    { id: deliveryTerms.id, type: deliveryTerms.type, value: source.deliveryTerms },
    { id: formValue(detailsField).id, type: formValue(detailsField).type, value: rows },
  ];
}

async function definition(): Promise<LarkApprovalDefinition> {
  const { approvalCode } = config();
  const result = await lark<LarkApprovalDefinition>(`/open-apis/approval/v4/approvals/${encodeURIComponent(approvalCode)}`);
  if (!result.form || !Array.isArray(result.node_list) || result.node_list.length === 0) {
    throw new Error("LARK_APPROVAL_DEFINITION_INVALID");
  }
  return result;
}

export async function openPurchaseApproval(input: {
  orchestrationId: string;
  supplierQuotationName: string;
  erpPurchaseOrderName: string;
  materialRequestName?: string;
  rfqName?: string;
  justification?: string;
}): Promise<{ instanceCode: string; erpPurchaseOrderName: string; idempotent: boolean }> {
  return lock(`open:${input.orchestrationId}`, async () => {
    const env = config();
    const source = await approvalSource(input);
    if (source.existingInstanceCode) {
      return { instanceCode: source.existingInstanceCode, erpPurchaseOrderName: source.purchaseOrderName, idempotent: true };
    }

    const approval = await definition();
    const submitter = await userId(supplierPortalConfig().approval_submitter_email);
    const approverEmail = LARK_PO_APPROVER_EMAIL;
    if (!approverEmail) throw new Error("LARK_PO_APPROVER_NOT_CONFIGURED");
    const approver = await userId(approverEmail);
    const approvalNodes = approval.node_list.filter((node) => stringValue(node.name).trim() === LARK_PO_APPROVAL_DESIGN.process.approvalNode.label);
    if (approvalNodes.length !== 1 || !stringValue(approvalNodes[0].node_id)) throw new Error("LARK_APPROVAL_NODE_INVALID");
    const nodes = approvalNodes.map((node) => ({ key: stringValue(node.node_id), value: [approver] }));

    const result = await lark<LarkApprovalCreateResult>("/open-apis/approval/v4/instances?user_id_type=user_id", {
      method: "POST",
      body: JSON.stringify({
        approval_code: env.approvalCode,
        user_id: submitter,
        form: JSON.stringify(approvalForm(approval.form, source)),
        uuid: createHash("sha256").update(`${source.orchestrationId}:${source.purchaseOrderName}`).digest("hex"),
        title: `Phê duyệt yêu cầu mua hàng - ${source.purchaseOrderName}`,
        node_approver_user_id_list: nodes,
      }),
    });
    const instanceCode = result.instance_code.trim();
    if (!instanceCode) throw new Error("LARK_APPROVAL_INSTANCE_CREATE_FAILED");

    await frappeUpdate("Purchase Order", source.purchaseOrderName, {
      custom_lark_approval_instance_code: instanceCode,
      custom_lark_approval_status: "Pending Approval",
      custom_lark_error: "",
    });
    await database().set(instanceKey(instanceCode), {
      purchase_order: source.purchaseOrderName,
      supplier_quotation: source.quotationName,
      material_request: source.materialRequestName,
      request_for_quotation: source.rfqName,
      source_fingerprint: source.sourceFingerprint,
    }, { ex: 90 * 86400 });
    return { instanceCode, erpPurchaseOrderName: source.purchaseOrderName, idempotent: false };
  });
}

export async function readPurchaseApproval(instanceCode: string): Promise<LarkApprovalInstance> {
  return lark<LarkApprovalInstance>(`/open-apis/approval/v4/instances/${encodeURIComponent(instanceCode)}?user_id_type=user_id`);
}

export async function submitApprovedPurchaseOrder(instanceCode: string, poName: string): Promise<{ name: string; idempotent: boolean }> {
  return lock(`submit:${poName}`, async () => {
    const po = await frappeGet<PurchaseOrder>("Purchase Order", poName);
    if (stringValue(po.custom_lark_approval_instance_code) !== instanceCode) throw new Error("ERP_PO_APPROVAL_MAPPING_MISMATCH");
    if (Number(po.docstatus ?? 0) === 1) return { name: poName, idempotent: true };
    if (Number(po.docstatus ?? 0) !== 0 || !stringValue(po.custom_letron_orchestration_id)) throw new Error("ERP_PO_NOT_SUBMITTABLE");
    const instance = await readPurchaseApproval(instanceCode);
    if (stringValue(instance.status).toUpperCase() !== "APPROVED") throw new Error("LARK_APPROVAL_NOT_APPROVED");
    const mapping = await database().get<Pick<ApprovalInstanceMapping, "supplier_quotation" | "material_request" | "request_for_quotation" | "source_fingerprint">>(instanceKey(instanceCode));
    if (!mapping?.supplier_quotation || !mapping.material_request || !mapping.request_for_quotation || !mapping.source_fingerprint) throw new Error("ERP_PO_APPROVAL_MAPPING_MISSING");
    const source = await approvalSource({ orchestrationId: stringValue(po.custom_letron_orchestration_id), supplierQuotationName: mapping.supplier_quotation, erpPurchaseOrderName: poName, materialRequestName: mapping.material_request, rfqName: mapping.request_for_quotation, justification: "approval-reconcile" });
    if (source.sourceFingerprint !== mapping.source_fingerprint) throw new Error("ERP_PO_APPROVAL_SOURCE_CHANGED");
    const submitted = await frappeDocumentAction<ErpSubmittedDocument>("Purchase Order", poName, "submit");
    if (Number(submitted.docstatus ?? 0) !== 1) throw new Error("ERP_PO_SUBMIT_NOT_CONFIRMED");
    await frappeUpdate("Purchase Order", poName, { custom_lark_approval_status: "Approved", custom_lark_error: "" });
    return { name: poName, idempotent: false };
  });
}

export async function markPurchaseApprovalState(poName: string, status: "Rejected" | "Canceled" | "ERP Failed", error = ""): Promise<void> {
  await frappeUpdate("Purchase Order", poName, { custom_lark_approval_status: status, custom_lark_error: error });
}

async function mappedPurchaseOrder(instanceCode: string): Promise<string> {
  const mapping = await database().get<{ purchase_order: string }>(instanceKey(instanceCode));
  if (!mapping?.purchase_order) throw new Error("ERP_PO_APPROVAL_MAPPING_MISSING");
  return mapping.purchase_order;
}

export async function reconcilePurchaseApproval(instanceCode: string): Promise<{ status: string; erpPurchaseOrderName: string }> {
  const instance = await readPurchaseApproval(instanceCode);
  const status = stringValue(instance.status).toUpperCase();
  const poName = await mappedPurchaseOrder(instanceCode);
  if (["REJECTED", "CANCELED", "CANCELLED"].includes(status)) {
    await markPurchaseApprovalState(poName, status === "REJECTED" ? "Rejected" : "Canceled");
    return { status, erpPurchaseOrderName: poName };
  }
  if (status !== "APPROVED") return { status, erpPurchaseOrderName: poName };
  await submitApprovedPurchaseOrder(instanceCode, poName);
  return { status: "ERP_SUBMITTED", erpPurchaseOrderName: poName };
}

export async function approvePurchaseApproval(instanceCode: string): Promise<{ status: string; taskId?: string; idempotent: boolean }> {
  const instance = await readPurchaseApproval(instanceCode);
  const status = stringValue(instance.status).toUpperCase();
  if (status === "APPROVED") return { status, idempotent: true };
  if (["REJECTED", "CANCELED", "CANCELLED"].includes(status)) throw new Error(`LARK_APPROVAL_ALREADY_${status}`);
  const email = LARK_PO_APPROVER_EMAIL;
  if (!email) throw new Error("LARK_PO_APPROVER_NOT_CONFIGURED");
  const approver = await userId(email);
  if (!Array.isArray(instance.task_list)) throw new Error("LARK_APPROVAL_TASKS_MISSING");
  const task = instance.task_list.find((item) => stringValue(item.status).toUpperCase() === "PENDING" && stringValue(item.user_id) === approver);
  const taskId = stringValue(task?.id);
  if (!taskId) throw new Error("LARK_APPROVAL_PENDING_TASK_NOT_FOUND");
  await lark("/open-apis/approval/v4/tasks/approve?user_id_type=user_id", { method: "POST", body: JSON.stringify({ approval_code: config().approvalCode, instance_code: instanceCode, user_id: approver, task_id: taskId, comment: "real-test auto-approved" }) });
  return { status: "APPROVED_REQUESTED", taskId, idempotent: false };
}

export function validApprovalWebhookSignature(body: string, timestamp: string, nonce: string, supplied: string): boolean {
  const key = stringValue(process.env.LETRON_INTERNAL_API_SECRET);
  if (!key || !timestamp || !nonce || !supplied || !/^\d+$/.test(timestamp) || Math.abs(Math.floor(Date.now() / 1000) - Number(timestamp)) > 300) return false;
  const expected = createHash("sha256").update(`${timestamp}${nonce}${key}${body}`).digest("hex");
  const actual = Buffer.from(supplied, "utf8");
  const expectedBuffer = Buffer.from(expected, "utf8");
  return actual.length === expectedBuffer.length && timingSafeEqual(actual, expectedBuffer);
}

export async function claimApprovalWebhook(eventId: string): Promise<"claimed" | "processing" | "completed"> {
  const key = `erp:lark-approval:event:${eventId}`;
  if (await database().set(key, "processing", { nx: true, ex: 120 })) return "claimed";
  return (await database().get<string>(key)) === "completed" ? "completed" : "processing";
}

export async function completeApprovalWebhook(eventId: string): Promise<void> {
  await database().set(`erp:lark-approval:event:${eventId}`, "completed", { ex: 7 * 86400 });
}

export async function releaseApprovalWebhook(eventId: string): Promise<void> {
  await database().del(`erp:lark-approval:event:${eventId}`);
}
