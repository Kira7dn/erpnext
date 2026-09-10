import { createHash, createHmac, randomUUID } from "node:crypto";

import { Redis } from "@upstash/redis";
import { z } from "zod";

import { getDb } from "./db";
import { getEnv } from "./env";
import { fetchLarkUserIdByEmail, larkTenantJson } from "./lark";
import { LARK_PO_APPROVAL_DESIGN } from "./lark-po-approval-design";

type Row = Record<string, unknown>;

const draftSchema = z.object({
  orchestration_id: z.string().min(1),
  material_request_name: z.string().min(1),
  request_for_quotation_name: z.string().optional().default(""),
  rfq_status: z.string().min(1).default("Draft"),
  supplier_quotation_name: z.string().optional().default(""),
  company: z.string().min(1),
  supplier: z.string().min(1),
  transaction_date: z.string().min(1),
  schedule_date: z.string().min(1),
  currency: z.string().min(1),
  conversion_rate: z.number().positive(),
  total_qty: z.number().positive(),
  net_total: z.number().nonnegative(),
  total_taxes: z.number().nonnegative().default(0),
  grand_total: z.number().nonnegative(),
  item_summary: z.string().min(1),
  payment_terms: z.string().optional().default(""),
  delivery_terms: z.string().optional().default(""),
  justification: z.string().min(1),
  portal_url: z.string().url(),
  items: z.array(z.record(z.string(), z.unknown())).min(1),
});

export type PoDraftInput = z.infer<typeof draftSchema>;

type RecordResponse = {
  data?: {
    record?: { record_id?: string; fields?: Record<string, unknown> };
  };
};
type ApprovalResponse = { data?: { instance_code?: string } };
type DraftRecord = { recordId: string; fields: Record<string, unknown> };

let lockStore: Redis | undefined;

function config() {
  const env = getEnv();
  if (
    !env.LARK_PO_BASE_APP_TOKEN ||
    !env.LARK_PO_DRAFT_TABLE_ID ||
    !env.LARK_PO_DRAFT_ITEM_TABLE_ID ||
    !env.LARK_PO_APPROVAL_CODE
  ) {
    throw new Error("LARK_PO_INTEGRATION_NOT_CONFIGURED");
  }
  return env as typeof env & {
    LARK_PO_BASE_APP_TOKEN: string;
    LARK_PO_DRAFT_TABLE_ID: string;
    LARK_PO_DRAFT_ITEM_TABLE_ID: string;
    LARK_PO_APPROVAL_CODE: string;
  };
}

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value as Row)
      .filter(([, item]) => item !== undefined)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, canonical(item)]),
  );
}

export function snapshotHash(input: PoDraftInput): string {
  return createHash("sha256")
    .update(JSON.stringify(canonical(input)))
    .digest("hex");
}

function basePath(app: string, table: string, suffix = ""): string {
  return `/open-apis/bitable/v1/apps/${encodeURIComponent(app)}/tables/${encodeURIComponent(table)}/records${suffix}`;
}

function larkLockStore(): Redis {
  if (lockStore) return lockStore;
  const env = getEnv();
  lockStore = new Redis({ url: env.KV_REST_API_URL, token: env.KV_REST_API_TOKEN });
  return lockStore;
}

async function withDraftLock<T>(orchestrationId: string, fn: () => Promise<T>): Promise<T> {
  const key = `letron:lark-po:lock:${createHash("sha256").update(orchestrationId).digest("hex")}`;
  const acquired = await larkLockStore().set(key, randomUUID(), { nx: true, ex: 90 });
  if (!acquired) throw new Error("LARK_PO_SUBMISSION_IN_PROGRESS");
  try {
    return await fn();
  } finally {
    await larkLockStore().del(key);
  }
}

export function parsePoDraft(input: unknown): PoDraftInput {
  return draftSchema.parse(input);
}

async function listDraftRecords(): Promise<DraftRecord[]> {
  const env = config();
  const records: DraftRecord[] = [];
  let pageToken = "";
  for (let page = 0; page < 20; page += 1) {
    const query = new URLSearchParams({ page_size: "500" });
    if (pageToken) query.set("page_token", pageToken);
    const result = await larkTenantJson<{
      data?: {
        items?: Array<{ record_id?: string; fields?: Record<string, unknown> }>;
        page_token?: string;
        has_more?: boolean;
      };
    }>(`${basePath(env.LARK_PO_BASE_APP_TOKEN, env.LARK_PO_DRAFT_TABLE_ID)}?${query}`);
    const data = result.data;
    for (const row of data?.items ?? []) {
      if (row.record_id) records.push({ recordId: row.record_id, fields: row.fields ?? {} });
    }
    if (!data?.has_more) return records;
    if (!data.page_token || data.page_token === pageToken)
      throw new Error("LARK_PO_DRAFT_PAGINATION_INVALID");
    pageToken = data.page_token;
  }
  throw new Error("LARK_PO_DRAFT_PAGINATION_LIMIT");
}

async function findDraftByCorrelation(orchestrationId: string): Promise<DraftRecord | null> {
  const records = await listDraftRecords();
  return (
    records.find((row) => String(row.fields.orchestration_id ?? "") === orchestrationId) ??
    null
  );
}

async function readDraftRecord(draftId: string): Promise<DraftRecord> {
  const env = config();
  const result = await larkTenantJson<RecordResponse>(
    basePath(
      env.LARK_PO_BASE_APP_TOKEN,
      env.LARK_PO_DRAFT_TABLE_ID,
      `/${encodeURIComponent(draftId)}`,
    ),
  );
  const fields = result.data?.record?.fields;
  if (!fields) throw new Error("LARK_PO_DRAFT_NOT_FOUND");
  return { recordId: draftId, fields };
}

async function readPoDraftItemRecords(draftId: string): Promise<DraftRecord[]> {
  const env = config();
  const result = await larkTenantJson<{
    data?: { items?: Array<{ record_id?: string; fields?: Record<string, unknown> }> };
  }>(
    `${basePath(env.LARK_PO_BASE_APP_TOKEN, env.LARK_PO_DRAFT_ITEM_TABLE_ID)}?page_size=500`,
  );
  return (result.data?.items ?? [])
    .filter(
      (row) =>
        row.record_id && String(row.fields?.po_draft_id ?? "") === draftId,
    )
    .map((row) => ({ recordId: row.record_id as string, fields: row.fields ?? {} }));
}

async function replaceDraftItems(
  draftId: string,
  items: Array<Record<string, unknown>>,
): Promise<void> {
  const env = config();
  const existing = await readPoDraftItemRecords(draftId);
  await Promise.all(
    items.map((item, index) => {
      const record = existing[index];
      return larkTenantJson(
        basePath(
          env.LARK_PO_BASE_APP_TOKEN,
          env.LARK_PO_DRAFT_ITEM_TABLE_ID,
          record ? `/${encodeURIComponent(record.recordId)}` : "",
        ),
        {
          method: record ? "PUT" : "POST",
          body: JSON.stringify({ fields: { po_draft_id: draftId, ...item } }),
        },
      );
    }),
  );
  await Promise.all(
    existing.slice(items.length).map((record) =>
      larkTenantJson(
        basePath(
          env.LARK_PO_BASE_APP_TOKEN,
          env.LARK_PO_DRAFT_ITEM_TABLE_ID,
          `/${encodeURIComponent(record.recordId)}`,
        ),
        { method: "DELETE" },
      ),
    ),
  );
}

function draftFields(input: PoDraftInput, hash: string, attempt: number): Row {
  return {
    draft_id: `PO-DRAFT-${input.orchestration_id}`,
    orchestration_id: input.orchestration_id,
    draft_status: "Pending Approval",
    material_request_name: input.material_request_name,
    request_for_quotation_name: input.request_for_quotation_name,
    supplier_quotation_name: input.supplier_quotation_name,
    company: input.company,
    supplier: input.supplier,
    transaction_date: input.transaction_date,
    schedule_date: input.schedule_date,
    currency: input.currency,
    conversion_rate: input.conversion_rate,
    total_qty: input.total_qty,
    net_total: input.net_total,
    total_taxes: input.total_taxes,
    grand_total: input.grand_total,
    item_summary: input.item_summary,
    payment_terms: input.payment_terms,
    delivery_terms: input.delivery_terms,
    justification: input.justification,
    portal_url: input.portal_url,
    snapshot_hash: hash,
    approval_attempt: attempt,
    approval_status: "PENDING",
    approval_instance_code: "",
    erp_purchase_order_name: "",
    erp_error: "",
    approval_submitted_at: new Date().toISOString(),
  };
}

export async function createPoDraft(
  input: PoDraftInput,
  existingDraftId?: string,
): Promise<{
  draftId: string;
  snapshotHash: string;
  attempt: number;
  idempotent: boolean;
}> {
  const env = config();
  const hash = snapshotHash(input);
  const existing = existingDraftId
    ? await readDraftRecord(existingDraftId)
    : await findDraftByCorrelation(input.orchestration_id);
  if (existing) {
    const currentHash = String(existing.fields.snapshot_hash ?? "");
    const currentAttempt = Math.max(
      1,
      Number(existing.fields.approval_attempt ?? 1),
    );
    const currentInstance = String(existing.fields.approval_instance_code ?? "");
    if (currentHash === hash && currentInstance) {
      return {
        draftId: existing.recordId,
        snapshotHash: hash,
        attempt: currentAttempt,
        idempotent: true,
      };
    }
    const attempt = currentHash === hash ? currentAttempt : currentAttempt + 1;
    await larkTenantJson(
      basePath(
        env.LARK_PO_BASE_APP_TOKEN,
        env.LARK_PO_DRAFT_TABLE_ID,
        `/${encodeURIComponent(existing.recordId)}`,
      ),
      {
        method: "PUT",
        body: JSON.stringify({
          fields: { ...draftFields(input, hash, attempt), draft_id: existing.recordId },
        }),
      },
    );
    await replaceDraftItems(existing.recordId, input.items);
    return {
      draftId: existing.recordId,
      snapshotHash: hash,
      attempt,
      idempotent: false,
    };
  }

  const result = await larkTenantJson<RecordResponse>(
    basePath(env.LARK_PO_BASE_APP_TOKEN, env.LARK_PO_DRAFT_TABLE_ID),
    {
      method: "POST",
      body: JSON.stringify({ fields: draftFields(input, hash, 1) }),
    },
  );
  const draftId = result.data?.record?.record_id;
  if (!draftId) throw new Error("LARK_PO_DRAFT_CREATE_FAILED");
  await updatePoDraft(draftId, { draft_id: draftId });
  await replaceDraftItems(draftId, input.items);
  return { draftId, snapshotHash: hash, attempt: 1, idempotent: false };
}

async function submitApproval(
  input: PoDraftInput,
  submitterEmail: string,
  existingDraftId?: string,
): Promise<{
  draftId: string;
  instanceCode: string;
  snapshotHash: string;
  attempt: number;
  idempotent: boolean;
}> {
  const env = config();
  const draft = await createPoDraft(input, existingDraftId);
  const current = await readDraftRecord(draft.draftId);
  const currentInstance = String(current.fields.approval_instance_code ?? "");
  if (draft.idempotent && currentInstance) {
    await saveDraftState({
      orchestrationId: input.orchestration_id,
      draftId: draft.draftId,
      approvalInstanceCode: currentInstance,
      approvalAttempt: draft.attempt,
      snapshotHash: draft.snapshotHash,
      status: String(current.fields.approval_status ?? "PENDING"),
    });
    return { ...draft, instanceCode: currentInstance };
  }

  const userId = await fetchLarkUserIdByEmail(submitterEmail);
  const definition = await readApprovalDefinition();
  const form = buildApprovalForm(definition.form, input, draft);
  const approvalNodes = Array.isArray(definition.node_list)
    ? definition.node_list.filter(
        (node): node is Row => Boolean(node && typeof node === "object" && text((node as Row).node_id)),
      )
    : [];
  const approverNodes = approvalNodes.filter((node) => node.need_approver === true);
  const approverEmail = env.LARK_PO_APPROVER_EMAIL;
  const nodeApprovers = approverNodes.length
    ? (() => {
        if (!approverEmail) throw new Error("LARK_PO_APPROVER_NOT_CONFIGURED");
        return fetchLarkUserIdByEmail(approverEmail).then((approverId) =>
          approverNodes.map((node) => ({
            key: text(node.node_id),
            value: [approverId],
          })),
        );
      })()
    : Promise.resolve(undefined);
  const nodeApproverUserIdList = await nodeApprovers;
  const result = await larkTenantJson<ApprovalResponse>(
    "/open-apis/approval/v4/instances?user_id_type=user_id",
    {
      method: "POST",
      body: JSON.stringify({
        approval_code: env.LARK_PO_APPROVAL_CODE,
        user_id: userId,
        form: JSON.stringify(form),
        uuid: createHash("sha256")
          .update(`${input.orchestration_id}:${draft.attempt}`)
          .digest("hex"),
        title: `Phê duyệt yêu cầu mua hàng - ${draft.draftId}`,
        ...(nodeApproverUserIdList
          ? { node_approver_user_id_list: nodeApproverUserIdList }
          : {}),
      }),
    },
  );
  const instanceCode = result.data?.instance_code;
  if (!instanceCode) throw new Error("LARK_APPROVAL_INSTANCE_CREATE_FAILED");
  await updatePoDraft(draft.draftId, {
    approval_instance_code: instanceCode,
    approval_status: "PENDING",
    draft_status: "Pending Approval",
    approval_attempt: draft.attempt,
    snapshot_hash: draft.snapshotHash,
  });
  await saveDraftState({
    orchestrationId: input.orchestration_id,
    draftId: draft.draftId,
    approvalInstanceCode: instanceCode,
    approvalAttempt: draft.attempt,
    snapshotHash: draft.snapshotHash,
    status: "PENDING",
    lastError: null,
  });
  return { ...draft, instanceCode };
}

async function readApprovalDefinition(): Promise<Record<string, unknown>> {
  const env = config();
  const result = await larkTenantJson<{ data?: Record<string, unknown> }>(
    `/open-apis/approval/v4/approvals/${encodeURIComponent(env.LARK_PO_APPROVAL_CODE)}`,
  );
  return result.data ?? {};
}

function parseApprovalFormFields(value: unknown): Array<Record<string, unknown>> {
  let parsed = value;
  if (typeof parsed === "string") {
    try {
      parsed = JSON.parse(parsed);
    } catch {
      return [];
    }
  }
  if (Array.isArray(parsed)) return parsed.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"));
  if (parsed && typeof parsed === "object" && Array.isArray((parsed as Row).form_content)) {
    return (parsed as Row).form_content as Array<Record<string, unknown>>;
  }
  return [];
}

function buildApprovalForm(
  definitionForm: unknown,
  input: PoDraftInput,
  draft: { draftId: string },
): Array<Record<string, unknown>> {
  const fields = parseApprovalFormFields(definitionForm);
  if (!fields.length) throw new Error("LARK_APPROVAL_FORM_NOT_CONFIGURED");
  const summary = input.portal_url;
  const normalized = (value: unknown) => text(value).replace(/\s+/g, " ").toLowerCase();
  const hasId = (field: Row, ids: string[]) =>
    ids.includes(text(field.id)) || ids.includes(text(field.custom_id));
  const byNameOrId = (name: string, ids: string[] = []) =>
    fields.find(
      (field) =>
        normalized(field.name) === normalized(name) || hasId(field, ids),
    );
  const byDesignKey = (designKey: string) => {
    const wanted = LARK_PO_APPROVAL_DESIGN.fields.find((field: { key: string }) => field.key === designKey);
    return wanted
      ? fields.find(
          (field) =>
            normalized(field.name) === normalized(wanted.label) || hasId(field, [wanted.sourceId]),
        )
      : undefined;
  };
  const purchaseDetails =
    byNameOrId("Purchase details", ["widget3"]) ??
    fields.find((field) => normalized(field.type) === "fieldlist");
  if (purchaseDetails && normalized(purchaseDetails.type) === "fieldlist") {
    const textareas = fields.filter((field) => normalized(field.type) === "textarea");
    const reason = byDesignKey("reason") ?? byNameOrId("Reason for purchase", ["widget0"]) ?? textareas[0];
    const referenceInfo = byDesignKey("reference") ?? byNameOrId("ERP reference information", ["widget16000000000001"]) ?? textareas[1];
    const purchaseType = byDesignKey("purchaseType") ?? byNameOrId("Purchase type", ["widget15754430770720001"]) ?? fields.find((field) => normalized(field.type) === "radiov2");
    const deliveryDate = byDesignKey("deliveryDate") ?? byNameOrId("Expected delivery date", ["widget2"]) ?? fields.find((field) => normalized(field.type) === "date");
    const paymentTerms = byDesignKey("paymentTerms") ?? byNameOrId("Payment terms", ["widget16000000000003"]) ?? textareas[2];
    const deliveryTerms = byDesignKey("deliveryTerms") ?? byNameOrId("Delivery terms", ["widget16000000000004"]) ?? textareas[3];
    const childrenValue = Array.isArray(purchaseDetails.children)
      ? purchaseDetails.children
      : Array.isArray(purchaseDetails.value)
        ? purchaseDetails.value
        : [];
    const children = childrenValue.filter(
          (field): field is Row => Boolean(field && typeof field === "object" && text((field as Row).id)),
        );
    const childByNameOrId = (name: string, ids: string[]) =>
      children.find(
        (field) =>
          normalized(field.name) === normalized(name) || hasId(field, ids),
      );
    const itemSummary = childByNameOrId("Item / specification", ["letron_po_item_summary"]);
    const supplierRfq = childByNameOrId("Supplier / RFQ", ["letron_po_supplier_rfq"]);
    const compactQuantity = childByNameOrId("Quantity", ["letron_po_qty"]);
    const compactUnitPrice = childByNameOrId("Unit price", ["letron_po_unit_price"]);
    const compactLineTotal = childByNameOrId("Line total", ["letron_po_line_total"]);
    const itemName = childByNameOrId("Item name", ["widget4"]) ?? children.find((field) => normalized(field.type) === "input");
    const specification = childByNameOrId("Specification", ["widget5"]) ?? children.filter((field) => normalized(field.type) === "textarea")[0];
    const quantity = childByNameOrId("Quantity", ["widget6"]) ?? children.find((field) => normalized(field.type) === "number");
    const itemSupplier = childByNameOrId("Supplier", ["letron_po_supplier"]);
    const rfqStatus = childByNameOrId("RFQ status", ["letron_po_rfq_status"]);
    const amountFields = children.filter((field) => normalized(field.type) === "amount");
    const unitPrice = childByNameOrId("Unit price", ["widget7"]) ?? amountFields[0];
    const lineTotal = childByNameOrId("Line total", ["widget16000000000005"]) ?? amountFields[1];
    const configuredCurrencies = Array.isArray((unitPrice?.option as Row | undefined)?.currencyRange)
      ? ((unitPrice?.option as Row).currencyRange as unknown[]).map(text).filter(Boolean)
      : [];
    const approvalCurrency = configuredCurrencies.includes(input.currency)
      ? input.currency
      : configuredCurrencies[0] || input.currency;
    const purchaseTypeOptions = Array.isArray(purchaseType?.option)
      ? purchaseType.option
      : Array.isArray(purchaseType?.value)
        ? purchaseType.value
        : [];
    const productionMaterials = purchaseTypeOptions.find(
          (option) =>
            (text((option as Row).value) || text((option as Row).key)) === "k3qy4q90-ya5zdx7hyh-3" ||
            ["production materials", "nguyên vật liệu sản xuất"].includes(
              normalized((option as Row).text),
            ),
        );
    const itemRows = input.items.map((item) => {
      const itemCode = text(item.item_code);
      const itemLabel = text(item.item_name) || itemCode;
      const specificationText = text(item.description) || "Không có mô tả";
      const itemQuantity = number(item.qty);
      const itemRate = number(item.rate);
      const itemAmount = itemQuantity * itemRate;
      if (itemSummary && supplierRfq && compactQuantity && compactUnitPrice && compactLineTotal) {
        return [
          { id: text(itemSummary.id), type: "input", value: `${itemLabel} | ${specificationText}` },
          { id: text(supplierRfq.id), type: "input", value: `${input.supplier} | RFQ: ${input.rfq_status}` },
          { id: text(compactQuantity.id), type: "input", value: String(itemQuantity) },
          { id: text(compactUnitPrice.id), type: "input", value: displayAmount(itemRate, approvalCurrency) },
          { id: text(compactLineTotal.id), type: "input", value: displayAmount(itemAmount, approvalCurrency) },
        ];
      }
      return [
        ...(itemName
          ? [{ id: text(itemName.id), type: text(itemName.type) || "input", value: itemLabel }]
          : []),
        ...(itemSupplier
          ? [{ id: text(itemSupplier.id), type: text(itemSupplier.type) || "input", value: input.supplier }]
          : []),
        ...(rfqStatus
          ? [{ id: text(rfqStatus.id), type: text(rfqStatus.type) || "input", value: input.rfq_status }]
          : []),
        ...(specification
          ? [{ id: text(specification.id), type: text(specification.type) || "input", value: specificationText }]
          : []),
        ...(quantity
          ? [{ id: text(quantity.id), type: text(quantity.type) || "number", value: itemQuantity }]
          : []),
        ...(unitPrice
          ? [{
              id: text(unitPrice.id),
              type: text(unitPrice.type) || "amount",
              value: itemRate,
              currency: approvalCurrency,
            }]
          : []),
        ...(lineTotal
          ? [{
              id: text(lineTotal.id),
              type: text(lineTotal.type) || "amount",
              value: itemQuantity * itemRate,
              currency: approvalCurrency,
            }]
          : []),
      ];
    });
    if (itemSummary && supplierRfq && compactQuantity && compactUnitPrice && compactLineTotal) {
      itemRows.push([
        { id: text(itemSummary.id), type: "input", value: LARK_PO_APPROVAL_DESIGN.table.totalLabel },
        { id: text(supplierRfq.id), type: "input", value: LARK_PO_APPROVAL_DESIGN.table.totalSupplier },
        { id: text(compactQuantity.id), type: "input", value: LARK_PO_APPROVAL_DESIGN.table.totalQuantity },
        { id: text(compactUnitPrice.id), type: "input", value: LARK_PO_APPROVAL_DESIGN.table.totalUnitPrice },
        { id: text(compactLineTotal.id), type: "input", value: displayAmount(input.net_total, approvalCurrency) },
      ]);
    }
    const purchaseForm = [
      ...(reason
        ? [{ id: text(reason.id), type: text(reason.type) || "textarea", value: input.justification }]
        : []),
      ...(referenceInfo
        ? [{ id: text(referenceInfo.id), type: text(referenceInfo.type) || "textarea", value: summary }]
        : []),
      ...(purchaseType
        ? [{
            id: text(purchaseType.id),
            type: text(purchaseType.type) || "radioV2",
            value:
              text((productionMaterials as Row | undefined)?.value) ||
              text((productionMaterials as Row | undefined)?.key) ||
              "production materials",
          }]
        : []),
      ...(deliveryDate
        ? [{
            id: text(deliveryDate.id),
            type: text(deliveryDate.type) || "date",
          value: `${input.schedule_date}T00:00:00+07:00`,
        }]
      : []),
      ...(paymentTerms
        ? [{ id: text(paymentTerms.id), type: text(paymentTerms.type) || "textarea", value: input.payment_terms || "Không có" }]
        : []),
      ...(deliveryTerms
        ? [{ id: text(deliveryTerms.id), type: text(deliveryTerms.type) || "textarea", value: input.delivery_terms || "Không có" }]
        : []),
      ...(purchaseDetails
        ? [{ id: text(purchaseDetails.id), type: text(purchaseDetails.type), value: itemRows }]
        : []),
    ];
    if (purchaseForm.length) return purchaseForm;
  }
  const values: Record<string, unknown> = {
    po_draft_id: draft.draftId,
    po_ref: summary,
    material_request: input.material_request_name,
    material_request_name: input.material_request_name,
    request_for_quotation: input.request_for_quotation_name,
    request_for_quotation_name: input.request_for_quotation_name,
    supplier: input.supplier,
    company: input.company,
    transaction_date: input.transaction_date,
    schedule_date: input.schedule_date,
    currency: input.currency,
    total_qty: input.total_qty,
    net_total: input.net_total,
    total_taxes: input.total_taxes,
    grand_total: input.grand_total,
    item_summary: input.item_summary,
    justification: input.justification,
    portal_url: input.portal_url,
  };
  const form = fields
    .map((field) => {
      const key = text(field.custom_id) || text(field.id);
      const value = values[key];
      if (!key || value === undefined) return null;
      const type = text(field.type) || "input";
      return {
        id: text(field.id),
        type,
        value: type === "number" || type === "amount" ? Number(value) : String(value),
        ...(type === "amount" ? { currency: input.currency } : {}),
      };
    })
    .filter((field) => field !== null);
  if (!form.length) throw new Error("LARK_APPROVAL_FORM_NOT_CONFIGURED");
  return form;
}

export async function submitPoDraftApproval(
  input: PoDraftInput,
  submitterEmail: string,
): Promise<{
  draftId: string;
  instanceCode: string;
  snapshotHash: string;
  attempt: number;
  idempotent: boolean;
}> {
  return withDraftLock(input.orchestration_id, () => submitApproval(input, submitterEmail));
}

export async function submitExistingPoDraftApproval(
  draftId: string,
  input: PoDraftInput,
  submitterEmail: string,
): Promise<{
  draftId: string;
  instanceCode: string;
  snapshotHash: string;
  attempt: number;
  idempotent: boolean;
}> {
  return withDraftLock(
    input.orchestration_id,
    () => submitApproval(input, submitterEmail, draftId),
  );
}

export async function readPoDraft(draftId: string): Promise<Record<string, unknown>> {
  return (await readDraftRecord(draftId)).fields;
}

export async function readPoDraftItems(draftId: string): Promise<Array<Record<string, unknown>>> {
  return (await readPoDraftItemRecords(draftId)).map((row) => row.fields);
}

export async function readApprovalInstance(
  instanceCode: string,
): Promise<Record<string, unknown>> {
  const result = await larkTenantJson<{ data?: Record<string, unknown> }>(
    `/open-apis/approval/v4/instances/${encodeURIComponent(instanceCode)}?user_id_type=user_id`,
  );
  return result.data ?? {};
}

export async function approvePoDraftApproval(instanceCode: string): Promise<{
  status: string;
  taskId?: string;
  idempotent: boolean;
}> {
  const env = config();
  const instance = await readApprovalInstance(instanceCode);
  const status = String(instance.status ?? instance.instance_status ?? "").toUpperCase();
  if (status === "APPROVED") return { status, idempotent: true };
  if (["REJECTED", "CANCELED", "CANCELLED"].includes(status)) {
    throw new Error(`LARK_APPROVAL_ALREADY_${status}`);
  }

  const approverEmail = env.LARK_PO_APPROVER_EMAIL;
  if (!approverEmail) throw new Error("LARK_PO_APPROVER_NOT_CONFIGURED");
  const approverId = await fetchLarkUserIdByEmail(approverEmail);
  const tasks = Array.isArray(instance.task_list)
    ? instance.task_list.filter((task): task is Row => Boolean(task && typeof task === "object"))
    : [];
  const task = tasks.find((candidate) => {
    const taskStatus = String(candidate.status ?? candidate.task_status ?? "").toUpperCase();
    const taskUserId = String(candidate.user_id ?? candidate.approver_user_id ?? "");
    return taskStatus === "PENDING" && taskUserId === approverId;
  });
  const taskId = String(task?.id ?? task?.task_id ?? "").trim();
  if (!taskId) throw new Error("LARK_APPROVAL_PENDING_TASK_NOT_FOUND");

  await larkTenantJson(
    "/open-apis/approval/v4/tasks/approve?user_id_type=user_id",
    {
      method: "POST",
      body: JSON.stringify({
        approval_code: env.LARK_PO_APPROVAL_CODE,
        instance_code: instanceCode,
        user_id: approverId,
        task_id: taskId,
        comment: "real-test auto-approved",
      }),
    },
  );
  return { status: "APPROVED_REQUESTED", taskId, idempotent: false };
}

export async function updatePoDraft(
  draftId: string,
  fields: Record<string, unknown>,
): Promise<void> {
  const env = config();
  await larkTenantJson(
    basePath(
      env.LARK_PO_BASE_APP_TOKEN,
      env.LARK_PO_DRAFT_TABLE_ID,
      `/${encodeURIComponent(draftId)}`,
    ),
    { method: "PUT", body: JSON.stringify({ fields }) },
  );
}

async function saveDraftState(input: {
  orchestrationId: string;
  draftId: string;
  approvalInstanceCode?: string;
  approvalAttempt: number;
  snapshotHash: string;
  status: string;
  erpPurchaseOrderName?: string | null;
  lastError?: string | null;
}): Promise<void> {
  await getDb().larkPoDraftState.upsert({
    where: { orchestrationId: input.orchestrationId },
    create: {
      orchestrationId: input.orchestrationId,
      draftId: input.draftId,
      approvalInstanceCode: input.approvalInstanceCode,
      approvalAttempt: input.approvalAttempt,
      snapshotHash: input.snapshotHash,
      status: input.status,
      erpPurchaseOrderName: input.erpPurchaseOrderName,
      lastError: input.lastError,
    },
    update: {
      draftId: input.draftId,
      approvalInstanceCode: input.approvalInstanceCode,
      approvalAttempt: input.approvalAttempt,
      snapshotHash: input.snapshotHash,
      status: input.status,
      erpPurchaseOrderName: input.erpPurchaseOrderName,
      lastError: input.lastError,
    },
  });
}

export async function markPoDraftStatus(input: {
  draftId: string;
  status: "APPROVED" | "REJECTED" | "CANCELED" | "ERP_FAILED" | "ERP_SUBMITTED";
  erpPurchaseOrderName?: string;
  error?: string;
}): Promise<void> {
  const draft = await readPoDraft(input.draftId);
  const orchestrationId = String(draft.orchestration_id ?? "");
  if (!orchestrationId) throw new Error("LARK_PO_ORCHESTRATION_ID_MISSING");
  await updatePoDraft(input.draftId, {
    approval_status: input.status === "CANCELED" ? "CANCELED" : input.status,
    draft_status:
      input.status === "ERP_SUBMITTED"
        ? "ERP Submitted"
        : input.status === "ERP_FAILED"
          ? "ERP Failed"
          : input.status === "CANCELED"
            ? "Canceled"
            : input.status[0] + input.status.slice(1).toLowerCase(),
    erp_purchase_order_name: input.erpPurchaseOrderName ?? "",
    erp_error: input.error ?? "",
    approval_completed_at: new Date().toISOString(),
  });
  await getDb().larkPoDraftState.updateMany({
    where: { orchestrationId },
    data: {
      status: input.status,
      erpPurchaseOrderName: input.erpPurchaseOrderName,
      lastError: input.error ?? null,
    },
  });
}

export async function claimLarkWebhookEvent(input: {
  eventId: string;
  eventType?: string;
  instanceCode?: string;
}): Promise<boolean> {
  try {
    await getDb().larkWebhookEvent.create({
      data: {
        eventId: input.eventId,
        eventType: input.eventType,
        instanceCode: input.instanceCode,
      },
    });
    return true;
  } catch {
    const existing = await getDb().larkWebhookEvent.findUnique({
      where: { eventId: input.eventId },
    });
    if (existing?.processedAt) return false;
    if (existing) {
      const claimed = await getDb().larkWebhookEvent.updateMany({
        where: { eventId: input.eventId, processedAt: null },
        data: {
          eventType: input.eventType,
          instanceCode: input.instanceCode,
        },
      });
      return claimed.count === 1;
    }
    throw new Error("LARK_WEBHOOK_DEDUPE_UNAVAILABLE");
  }
}

export async function completeLarkWebhookEvent(eventId: string): Promise<void> {
  await getDb().larkWebhookEvent.update({
    where: { eventId },
    data: { processedAt: new Date() },
  });
}

async function gatewayJson<T>(path: string, cookieHeader: string): Promise<T> {
  const env = getEnv();
  const serverHeaders = !cookieHeader ? controlHeaders(path, "GET") : {};
  const response = await fetch(
    new URL(cookieHeader ? `/api/gateway${path}` : path, cookieHeader ? `${env.AUTH_BASE_URL}/` : `${env.LETRON_SSO_ERP_BASE_URL ?? ""}/`),
    {
      headers: {
        Accept: "application/json",
        ...serverHeaders,
        ...( /^Bearer\s+\S+$/i.test(cookieHeader)
          ? { Authorization: cookieHeader }
          : { Cookie: cookieHeader }),
      },
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    },
  );
  const payload = (await response.json().catch(() => ({}))) as {
    data?: T;
    message?: T;
  };
  if (!response.ok) throw new Error(`ERP_SOURCE_READ_FAILED_${response.status}`);
  return (payload.data ?? payload.message) as T;
}

async function supplierSourceJson<T>(payload: Record<string, unknown>): Promise<T> {
  const env = getEnv();
  const path = "/api/method/letron_api.supplier_portal.read_approval_source";
  if (!env.LETRON_SSO_ERP_BASE_URL) throw new Error("ERP_SOURCE_READ_FAILED_503");
  const response = await fetch(new URL(path, `${env.LETRON_SSO_ERP_BASE_URL}/`), {
    method: "POST",
    headers: { Accept: "application/json", ...controlHeaders(path) },
    body: JSON.stringify(payload),
    cache: "no-store",
    signal: AbortSignal.timeout(30_000),
  });
  const result = await response.json().catch(() => ({})) as { message?: T; data?: T };
  if (!response.ok) throw new Error(`ERP_SOURCE_READ_FAILED_${response.status}`);
  return (result.data ?? result.message) as T;
}

async function sourceByCorrelation(
  path: string,
  doctype: string,
  orchestrationId: string,
  cookieHeader: string,
): Promise<Row> {
  if (!cookieHeader) {
    const source = await supplierSourceJson<{ material_request?: Row; rfq?: Row }>({ orchestration_id: orchestrationId });
    const value = doctype === "Material Request" ? source.material_request : source.rfq;
    if (!value) throw new Error("ERP_SOURCE_CORRELATION_NOT_FOUND");
    return value;
  }
  const query = new URLSearchParams({
    filters: JSON.stringify([
      [doctype, "custom_letron_orchestration_id", "=", orchestrationId],
    ]),
    fields: JSON.stringify(["name"]),
    limit_page_length: "10",
  });
  const rows = await gatewayJson<Row[]>(`${path}?${query}`, cookieHeader);
  if (!Array.isArray(rows) || rows.length !== 1) {
    throw new Error(
      rows?.length
        ? "ERP_SOURCE_CORRELATION_NOT_UNIQUE"
        : "ERP_SOURCE_CORRELATION_NOT_FOUND",
    );
  }
  const name = String(rows[0].name ?? "");
  if (!name) throw new Error("ERP_SOURCE_NAME_MISSING");
  return gatewayJson<Row>(`${path}/${encodeURIComponent(name)}`, cookieHeader);
}

async function sourceByName(
  path: string,
  name: string,
  cookieHeader: string,
): Promise<Row> {
  if (!cookieHeader) {
    const source = await supplierSourceJson<{ supplier_quotation?: Row }>({ supplier_quotation_name: name, orchestration_id: "" });
    if (!source.supplier_quotation) throw new Error("ERP_SOURCE_NAME_MISSING");
    return source.supplier_quotation;
  }
  return gatewayJson<Row>(`${path}/${encodeURIComponent(name)}`, cookieHeader);
}

function text(value: unknown): string {
  return String(value ?? "").trim();
}

function nestedText(value: unknown, names: string[]): string | undefined {
  if (typeof value === "string" && value.trim().startsWith("[")) {
    try {
      return nestedText(JSON.parse(value), names);
    } catch {
      return undefined;
    }
  }
  if (!value || typeof value !== "object") return undefined;
  const row = value as Row;
  for (const name of names) {
    const candidate = row[name];
    if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
  }
  for (const child of Object.values(row)) {
    const found = nestedText(child, names);
    if (found) return found;
  }
  return undefined;
}

function number(value: unknown, fallback = 0): number {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}

function displayAmount(value: number, currency: string): string {
  return `${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
}

function maxDate(values: string[], fallback: string): string {
  const dates = values.filter((value) => /^\d{4}-\d{2}-\d{2}$/.test(value));
  return dates.sort().at(-1) ?? fallback;
}

export async function buildPoDraftFromCorrelation(input: {
  orchestrationId: string;
  supplierQuotationName?: string;
  justification?: string;
  portalUrl?: string;
  cookieHeader: string;
}): Promise<PoDraftInput> {
  const materialRequest = await sourceByCorrelation(
    "/api/v1/stock/material-requests",
    "Material Request",
    input.orchestrationId,
    input.cookieHeader,
  );
  const rfq = await sourceByCorrelation(
    "/api/v1/crm/request-for-quotations",
    "Request for Quotation",
    input.orchestrationId,
    input.cookieHeader,
  );
  const supplierQuotationName = text(input.supplierQuotationName);
  const supplierQuotation = supplierQuotationName
    ? await sourceByName(
        "/api/v1/crm/supplier-quotations",
        supplierQuotationName,
        input.cookieHeader,
      )
    : null;
  const mrName = text(materialRequest.name);
  const rfqName = text(rfq.name);
  const sqName = text(supplierQuotation?.name);
  const transactionDate =
    text(supplierQuotation?.transaction_date) ||
    text(rfq.transaction_date) ||
    text(materialRequest.transaction_date);
  const company =
    text(supplierQuotation?.company) || text(rfq.company) || text(materialRequest.company);
  const rfqSuppliers = Array.isArray(rfq.suppliers) ? rfq.suppliers : [];
  const supplier =
    text(supplierQuotation?.supplier) || text((rfqSuppliers[0] as Row | undefined)?.supplier);
  if (!mrName || !rfqName || !company || !supplier || !transactionDate)
    throw new Error("LARK_PO_SOURCE_FIELDS_INCOMPLETE");
  if (
    company !== text(materialRequest.company) ||
    company !== text(rfq.company)
  )
    throw new Error("LARK_PO_SOURCE_COMPANY_MISMATCH");
  if (!rfqSuppliers.some((row) => text((row as Row).supplier) === supplier))
    throw new Error("LARK_PO_SUPPLIER_NOT_IN_RFQ");
  const mrItems = Array.isArray(materialRequest.items) ? materialRequest.items : [];
  const rfqItems = Array.isArray(rfq.items) ? rfq.items : [];
  const quoteItems = supplierQuotation && Array.isArray(supplierQuotation.items)
    ? supplierQuotation.items
    : [];
  if (!mrItems.length || !rfqItems.length || (supplierQuotation && !quoteItems.length))
    throw new Error("LARK_PO_SOURCE_ITEMS_INCOMPLETE");
  const mrByName = new Map(
    mrItems.map((row) => [text((row as Row).name), row as Row]),
  );
  const rfqByName = new Map(
    rfqItems.map((row) => [text((row as Row).name), row as Row]),
  );
  const items = (supplierQuotation ? quoteItems : rfqItems).map((raw, index) => {
    const source = raw as Row;
    const mrItemName = text(source.material_request_item) || text(mrItems[index]?.name);
    const rfqItemName = supplierQuotation
      ? text(source.request_for_quotation_item) || text(rfqItems[index]?.name)
      : text(source.name) || text(rfqItems[index]?.name);
    const mrItem = mrByName.get(mrItemName) || (mrItems[index] as Row | undefined);
    const rfqItem = rfqByName.get(rfqItemName) || (rfqItems[index] as Row | undefined);
    if (!mrItem || !rfqItem || text(rfqItem.material_request) !== mrName)
      throw new Error("LARK_PO_SOURCE_ITEM_LINK_MISMATCH");
    if (supplierQuotation && (
      text(source.material_request) !== mrName ||
      text(source.request_for_quotation) !== rfqName ||
      text(rfqItem.material_request_item) !== mrItemName
    ))
      throw new Error("LARK_PO_SOURCE_ITEM_LINK_MISMATCH");
    const qty = number(source.qty, number(rfqItem.qty, number(mrItem.qty)));
    const rate = number(
      source.rate,
      number(source.base_rate, number(rfqItem.rate, number(mrItem.rate, number(mrItem.price_list_rate)))),
    );
    if (!text(source.item_code) && !text(rfqItem.item_code) && !text(mrItem.item_code))
      throw new Error("LARK_PO_SOURCE_ITEM_INVALID");
    if (qty <= 0 || rate < 0) throw new Error("LARK_PO_SOURCE_ITEM_INVALID");
    return {
      item_code: text(source.item_code) || text(rfqItem.item_code) || text(mrItem.item_code),
      item_name: text(source.item_name) || text(source.description) || text(rfqItem.item_name) || text(mrItem.item_name),
      description: text(source.description) || text(rfqItem.description) || text(mrItem.description),
      qty,
      uom: text(source.uom) || text(rfqItem.uom) || text(mrItem.uom),
      stock_uom: text(source.stock_uom) || text(rfqItem.stock_uom) || text(mrItem.stock_uom),
      conversion_factor: number(
        source.conversion_factor,
        number(rfqItem.conversion_factor, number(mrItem.conversion_factor, 1)),
      ),
      rate,
      amount: number(source.amount, qty * rate),
      warehouse: text(source.warehouse) || text(rfqItem.warehouse) || text(mrItem.warehouse),
      material_request: mrName,
      material_request_item: mrItemName,
      request_for_quotation: rfqName,
      request_for_quotation_item: rfqItemName,
      supplier_quotation: sqName,
      supplier_quotation_item: supplierQuotation ? text(source.name) : "",
    };
  });
  const itemSummary = items
    .map(
      (item, index) =>
        `${index + 1}. ${item.item_code} | ${item.item_name} | qty=${item.qty} | UOM=${item.uom} | rate=${item.rate} | amount=${item.amount} | ${item.warehouse}`,
    )
    .join("\n");
  const scheduleDate = maxDate(
    items.map((item) => text((rfqByName.get(item.request_for_quotation_item) as Row | undefined)?.schedule_date),
    ),
    text(rfq.schedule_date) || text(materialRequest.schedule_date) || transactionDate,
  );
  if (scheduleDate < transactionDate) throw new Error("LARK_PO_SCHEDULE_BEFORE_TRANSACTION");
  const env = getEnv();
  const portalUrl =
    input.portalUrl ||
    `${env.LETRON_NEXT_BASE_URL ?? env.AUTH_BASE_URL}/purchase/requests?orchestration=${encodeURIComponent(input.orchestrationId)}`;
  const parsed = {
    orchestration_id: input.orchestrationId,
    material_request_name: mrName,
    request_for_quotation_name: rfqName,
    rfq_status: text(rfq.status) || "Draft",
    supplier_quotation_name: sqName,
    company,
    supplier,
    transaction_date: transactionDate,
    schedule_date: scheduleDate,
    currency: text(supplierQuotation?.currency) || text(rfq.currency) || text(materialRequest.currency) || "VND",
    conversion_rate: number(supplierQuotation?.conversion_rate, 1),
    total_qty: items.reduce((total, item) => total + item.qty, 0),
    net_total: number(
      supplierQuotation?.net_total,
      items.reduce((total, item) => total + item.amount, 0),
    ),
    total_taxes: number(supplierQuotation?.total_taxes_and_charges),
    grand_total: number(
      supplierQuotation?.grand_total,
      number(supplierQuotation?.net_total, items.reduce((total, item) => total + item.amount, 0)) +
        number(supplierQuotation?.total_taxes_and_charges),
    ),
    item_summary: itemSummary,
    payment_terms: text(supplierQuotation?.terms) || text(rfq.terms),
    delivery_terms: [
      text(supplierQuotation?.incoterm) || text(rfq.incoterm),
      text(supplierQuotation?.named_place) || text(rfq.named_place),
    ]
      .filter(Boolean)
      .join(" / "),
    justification:
      text(input.justification) ||
        (sqName ? `Chọn báo giá ${sqName} cho RFQ ${rfqName}` : `Phê duyệt yêu cầu mua hàng ${mrName}`),
    portal_url: portalUrl,
    items,
  };
  return parsePoDraft(parsed);
}

function controlHeaders(path: string, method = "POST"): Record<string, string> {
  const env = getEnv();
  const secret = env.LETRON_SSO_SYNC_SECRET ?? env.AUTH_ERP_SYNC_SECRET;
  if (!env.LETRON_SSO_ERP_BASE_URL || !secret)
    throw new Error("ERP_APPROVED_PO_NOT_CONFIGURED");
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const expires = String(Number(timestamp) + 60);
  const requestId = randomUUID();
  const signature = createHmac("sha256", secret)
    .update(`${timestamp}.${expires}.${method}.${path}.${requestId}`)
    .digest("hex");
  return {
    "content-type": "application/json",
    "X-Letron-Control-Timestamp": timestamp,
    "X-Letron-Control-Expires-At": expires,
    "X-Letron-Control-Request-Id": requestId,
    "X-Letron-Control-Signature": signature,
  };
}

export async function createApprovedErpPurchaseOrder(input: {
  approval_instance_code: string;
  snapshot_hash: string;
  attempt: number;
  draft: Record<string, unknown>;
  items: Array<Record<string, unknown>>;
}): Promise<Record<string, unknown>> {
  const env = getEnv();
  const path = "/api/method/letron_api.lark_po.from_approved";
  const response = await fetch(new URL(path, `${env.LETRON_SSO_ERP_BASE_URL}/`), {
    method: "POST",
    headers: controlHeaders(path),
    body: JSON.stringify(input),
    signal: AbortSignal.timeout(30_000),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload && typeof payload === "object"
      ? String(
          (payload as Row).exc ??
          (payload as Row)._server_messages ??
          (payload as Row).message ??
          (payload as Row).exception ??
          (payload as Row).exc_type ??
          "",
        ).trim()
      : "";
    throw new Error(`ERP_APPROVED_PO_FAILED_${response.status}${detail ? `: ${detail.slice(0, 500)}` : ""}`);
  }
  return payload as Record<string, unknown>;
}

export async function reconcileApprovedPoDraft(instanceCode: string): Promise<{
  status: string;
  erpPurchaseOrderName?: string;
}> {
  const instance = await readApprovalInstance(instanceCode);
  const status = String(instance.status ?? instance.instance_status ?? "").toUpperCase();
  const state = await getDb().larkPoDraftState.findFirst({
    where: { approvalInstanceCode: instanceCode },
  });
  const draftId = nestedText(instance, ["po_draft_id"]) ?? state?.draftId ?? undefined;
  if (!draftId) throw new Error("PO_DRAFT_ID_MISSING");
  const draft = await readPoDraft(draftId);
  const draftInstance = String(draft.approval_instance_code ?? "");
  const draftAttempt = Number(draft.approval_attempt ?? 0);
  const instanceAttempt = Number(nestedText(instance, ["approval_attempt"]) ?? draftAttempt);
  const draftHash = String(draft.snapshot_hash ?? "");
  const instanceHash = nestedText(instance, ["snapshot_hash"]);
  if (
    draftInstance !== instanceCode ||
    draftAttempt !== instanceAttempt ||
    draftHash.length !== 64 ||
    (instanceHash !== undefined && instanceHash !== draftHash)
  ) {
    throw new Error("APPROVAL_SNAPSHOT_SUPERSEDED");
  }
  if (status === "REJECTED" || status === "CANCELED" || status === "CANCELLED") {
    await markPoDraftStatus({ draftId, status: status === "REJECTED" ? "REJECTED" : "CANCELED" });
    return { status };
  }
  if (status !== "APPROVED") return { status };
  const result = await createApprovedErpPurchaseOrder({
    approval_instance_code: instanceCode,
    snapshot_hash: draftHash,
    attempt: draftAttempt,
    draft,
    items: await readPoDraftItems(draftId),
  });
  const resultRow = result as Row;
  const resultData = resultRow.data ?? resultRow.message ?? resultRow;
  const poName = String(
    resultData && typeof resultData === "object" ? (resultData as Row).name ?? "" : "",
  );
  if (!poName) throw new Error("ERP_APPROVED_PO_NAME_MISSING");
  await markPoDraftStatus({ draftId, status: "ERP_SUBMITTED", erpPurchaseOrderName: poName });
  return { status: "ERP_SUBMITTED", erpPurchaseOrderName: poName };
}
