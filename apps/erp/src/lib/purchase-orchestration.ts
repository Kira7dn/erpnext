import "server-only";

import { createHash } from "node:crypto";
import { Redis } from "@upstash/redis";
import {
  GatewayAccessDeniedError,
  GatewayAuthenticationRequiredError,
  GatewayRequestError,
  GatewayUnavailableError,
  gatewayRequest,
  validatedGatewayRequest,
} from "@/lib/letron-api";
import { ApiRequestError } from "@/lib/api-error";
import { sendSupplierPortalMail } from "@/lib/supplier-portal";
import { buildAccessMail } from "@/lib/supplier-portal-session";
import { ensureSupplierPortalAccess, resolveSupplierEmail } from "@/lib/supplier-portal-core";
import {
  MaterialRequestResponseSchema,
  MaterialRequestWriteSchema,
  ItemResponseSchema,
  RequestforQuotationResponseSchema,
  RequestforQuotationWriteSchema,
} from "@/generated/zod";
import {
  buildRfqPayload,
  hydrateRfqItems,
  itemsFromCreatedMaterialRequest,
} from "@/lib/purchase-orchestration-contract";

type Row = Record<string, unknown>;
type Item = {
  name?: string;
  item_code: string;
  qty: number;
  schedule_date?: string;
  warehouse?: string;
  uom?: string;
  stock_uom?: string;
  conversion_factor?: number;
  rate?: number;
  material_request?: string;
  material_request_item?: string;
};
export type PurchaseOrchestrationInput = {
  material_request: Row;
  suppliers: string[];
  justification?: string;
};
export type PurchaseOrchestrationState = {
  id: string;
  status: "started" | "mr_created" | "partial_failure" | "rfq_created" | "waiting_supplier_quotes" | "failed";
  material_request: Row;
  suppliers: string[];
  rfq_payload: Row;
  material_request_name?: string;
  request_for_quotation_name?: string;
  supplier_quote_deadline_at?: string;
  mail_deliveries?: Array<{ supplier: string; to: string; subject: string; message_id: string; idempotent?: boolean }>;
  justification?: string;
  retry_count: number;
  error?: string;
  created_at: string;
  updated_at: string;
};

const STATE_TTL_SECONDS = 7 * 24 * 60 * 60;
const PREFIX = "erp:purchase:orchestration:";
let redis: Redis | undefined;

function store(): Redis {
  if (redis) return redis;
  const url = process.env.KV_REST_API_URL;
  const token = process.env.KV_REST_API_TOKEN;
  if (!url || !token)
    throw new ApiRequestError("configuration_error", "Purchase orchestration storage is not configured.", 503);
  redis = new Redis({ url, token });
  return redis;
}

function ownerHash(cookieHeader: string): string {
  return createHash("sha256").update(cookieHeader).digest("hex").slice(0, 32);
}

function activeIndex(cookieHeader: string): string {
  return `${PREFIX}active:${ownerHash(cookieHeader)}`;
}

function stateKey(cookieHeader: string, idempotencyKey: string): string {
  const keyHash = createHash("sha256").update(idempotencyKey).digest("hex");
  return `${PREFIX}${ownerHash(cookieHeader)}:${keyHash}`;
}

function retryKey(key: string): string {
  return `${key}:rfq-retry`;
}

function correlationId(idempotencyKey: string): string {
  return createHash("sha256").update(idempotencyKey).digest("hex").slice(0, 32);
}

function idKey(cookieHeader: string, id: string): string {
  return `${PREFIX}id:${ownerHash(cookieHeader)}:${id}`;
}

export class PurchaseOrchestrationValidationError extends Error {}

function normalizeInput(input: PurchaseOrchestrationInput): {
  materialRequest: Row;
  suppliers: string[];
  items: Item[];
} {
  const materialRequest = input?.material_request;
  const suppliers = Array.isArray(input?.suppliers)
    ? [
        ...new Set(
          input.suppliers
            .map(String)
            .map((value) => value.trim())
            .filter(Boolean),
        ),
      ]
    : [];
  const sourceItems = Array.isArray(materialRequest?.items)
    ? materialRequest.items
    : [];
  const items = sourceItems.map((item) => ({
    item_code: String((item as Row).item_code ?? "").trim(),
    qty: Number((item as Row).qty),
    schedule_date:
      String((item as Row).schedule_date ?? "").trim() || undefined,
    warehouse: String((item as Row).warehouse ?? "").trim() || undefined,
    uom: String((item as Row).uom ?? "").trim() || undefined,
    stock_uom: String((item as Row).stock_uom ?? "").trim() || undefined,
    conversion_factor: Number((item as Row).conversion_factor) || 1,
    rate: Number((item as Row).rate ?? (item as Row).price_list_rate) || 0,
  }));
  if (!materialRequest || typeof materialRequest !== "object")
    throw new PurchaseOrchestrationValidationError(
      "material_request is required.",
    );
  for (const field of [
    "company",
    "material_request_type",
    "transaction_date",
  ]) {
    if (!String(materialRequest[field] ?? "").trim())
      throw new PurchaseOrchestrationValidationError(`${field} is required.`);
  }
  if (
    !items.length ||
    items.some(
      (item) => !item.item_code || !Number.isFinite(item.qty) || item.qty <= 0,
    )
  ) {
    throw new PurchaseOrchestrationValidationError(
      "At least one valid Material Request item is required.",
    );
  }
  if (!suppliers.length)
    throw new PurchaseOrchestrationValidationError(
      "At least one Supplier is required.",
    );
  return { materialRequest: { ...materialRequest, items }, suppliers, items };
}

async function findByCorrelation(
  path: string,
  cookieHeader: string,
  orchestrationId: string,
): Promise<Row | null> {
  const filters = encodeURIComponent(
    JSON.stringify([[path.includes("material-requests") ? "Material Request" : "Request for Quotation", "custom_letron_orchestration_id", "=", orchestrationId]]),
  );
  const fields = encodeURIComponent(JSON.stringify(["name"]));
  const result = await gatewayRequest<unknown>(
    `${path}?filters=${filters}&fields=${fields}&limit_page_length=2`,
    cookieHeader,
  );
  if (!Array.isArray(result)) return null;
  for (const candidate of result.slice(0, 25)) {
    if (!candidate || typeof candidate !== "object") continue;
    const name = String((candidate as Row).name ?? "");
    if (!name) continue;
    const detail = await gatewayRequest<Row>(
      `${path}/${encodeURIComponent(name)}`,
      cookieHeader,
    );
    if (String(detail.custom_letron_orchestration_id ?? "") === orchestrationId)
      return detail;
  }
  return null;
}

async function saveState(
  key: string,
  state: PurchaseOrchestrationState,
): Promise<void> {
  state.updated_at = new Date().toISOString();
  await store().set(key, state, { ex: STATE_TTL_SECONDS });
  const owner = key.slice(PREFIX.length).split(":")[0];
  const index = `${PREFIX}active:${owner}`;
  await store().sadd(index, key);
}

function stateResult(
  state: PurchaseOrchestrationState,
): PurchaseOrchestrationState {
  return structuredClone(state);
}

function errorMessage(cause: unknown): string {
  return cause instanceof ApiRequestError ? cause.message : "ERP purchase operation failed.";
}

async function issueSupplierPortalAccesses(
  state: PurchaseOrchestrationState,
  materialRequest: Row,
): Promise<void> {
  const createdAt = new Date(String(materialRequest.creation ?? state.created_at));
  const quotationDeadline = new Date(createdAt.getTime() + 3 * 24 * 60 * 60 * 1000).toISOString();
  const accessExpiry = new Date(createdAt.getTime() + 30 * 24 * 60 * 60 * 1000).toISOString();
  for (const supplier of state.suppliers) {
    const result = await ensureSupplierPortalAccess({
      material_request: state.material_request_name ?? "",
      request_for_quotation: state.request_for_quotation_name ?? "",
      orchestration_id: state.id,
      supplier,
      email: await resolveSupplierEmail(supplier),
      deadline_at: quotationDeadline,
      access_expires_at: accessExpiry,
    });
    if (!result.access.access_id || !result.access.email) throw new ApiRequestError("supplier_portal_access_missing", "Supplier portal access is missing.", 502);
    const mail = buildAccessMail(result.access, result.magic_token);
    const delivery = await sendSupplierPortalMail(mail);
    const deliveries = (state.mail_deliveries ?? []).filter((item) => item.supplier !== supplier);
    state.mail_deliveries = [...deliveries, { supplier, to: mail.to, subject: mail.subject, message_id: delivery.messageId, idempotent: delivery.idempotent }];
  }
  state.supplier_quote_deadline_at = quotationDeadline;
}

export function orchestrationHttpStatus(cause: unknown): number {
  if (cause instanceof PurchaseOrchestrationValidationError) return 400;
  if (cause instanceof GatewayAuthenticationRequiredError) return 401;
  if (cause instanceof GatewayAccessDeniedError) return 403;
  if (cause instanceof GatewayUnavailableError) return 503;
  if (cause instanceof GatewayRequestError) return cause.status >= 500 ? 502 : 400;
  return 502;
}

export async function createPurchaseOrchestration(
  cookieHeader: string,
  input: PurchaseOrchestrationInput,
  idempotencyKey: string,
): Promise<PurchaseOrchestrationState> {
  if (!idempotencyKey.trim())
    throw new PurchaseOrchestrationValidationError(
      "X-Idempotency-Key is required.",
    );
  const normalized = normalizeInput(input);
  const key = stateKey(cookieHeader, idempotencyKey);
  const existing = await store().get<PurchaseOrchestrationState>(key);
  if (existing) {
    if (existing.status !== "started") return stateResult(existing);
    return continueStartedOrchestration(cookieHeader, idempotencyKey, key, existing);
  }
  const now = new Date().toISOString();
  const state: PurchaseOrchestrationState = {
    id: correlationId(idempotencyKey),
    status: "started",
    material_request: normalized.materialRequest,
    suppliers: normalized.suppliers,
    justification: String(input.justification ?? "").trim() || undefined,
    // The RFQ contract requires ERP-derived stock_uom values. Build and
    // validate it only after the Material Request has been created/read back.
    rfq_payload: {},
    retry_count: 0,
    created_at: now,
    updated_at: now,
  };
  const claimed = await store().set(key, state, {
    nx: true,
    ex: STATE_TTL_SECONDS,
  });
  if (!claimed) {
    const concurrent = await store().get<PurchaseOrchestrationState>(key);
    if (concurrent) return stateResult(concurrent);
    throw new ApiRequestError("orchestration_claim_failed", "Purchase orchestration could not be claimed.", 409);
  }
  await store().sadd(activeIndex(cookieHeader), key);
  await store().set(idKey(cookieHeader, state.id), idempotencyKey, {
    ex: STATE_TTL_SECONDS,
  });
  try {
    const materialRequestPayload = MaterialRequestWriteSchema.parse({
      ...normalized.materialRequest,
      items: normalized.items.map(({ stock_uom, ...item }) => {
        void stock_uom;
        return item;
      }),
      naming_series: "MR-.YYYYMMDD.-.####",
      custom_letron_orchestration_id: state.id,
    });
    const materialRequest = await validatedGatewayRequest<Row>(
      "/api/v1/stock/material-requests",
      MaterialRequestResponseSchema,
      cookieHeader,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Idempotency-Key": `${idempotencyKey}:mr`,
        },
        body: JSON.stringify(materialRequestPayload),
      },
    );
    state.material_request_name = String(materialRequest.name ?? "");
    state.rfq_payload = buildRfqPayload(
      normalized.materialRequest,
      normalized.suppliers,
      await hydrateRfqItems(
        itemsFromCreatedMaterialRequest(materialRequest),
        (itemCode) => validatedGatewayRequest<Row>(
          `/api/v1/stock/items/${encodeURIComponent(itemCode)}`,
          ItemResponseSchema,
          cookieHeader,
        ),
      ),
      state.id,
    );
    state.status = "mr_created";
    await saveState(key, state);
    const rfq = await validatedGatewayRequest<Row>(
      "/api/v1/crm/request-for-quotations",
      RequestforQuotationResponseSchema,
      cookieHeader,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Idempotency-Key": `${idempotencyKey}:rfq`,
        },
        body: JSON.stringify(state.rfq_payload),
      },
    );
    state.request_for_quotation_name = String(rfq.name ?? "");
    await issueSupplierPortalAccesses(state, materialRequest);
    state.status = "waiting_supplier_quotes";
    state.supplier_quote_deadline_at = new Date(
      Date.parse(state.created_at) + 3 * 24 * 60 * 60 * 1000,
    ).toISOString();
    await saveState(key, state);
    return stateResult(state);
  } catch (cause) {
    const hasMr = Boolean(state.material_request_name);
    state.status = hasMr ? "partial_failure" : "failed";
    state.error = errorMessage(cause);
    console.error("[purchase-orchestration] orchestration failed", {
      correlation_id: state.id,
      stage: state.status,
      error_code: cause instanceof ApiRequestError ? cause.code : "internal_error",
      error_message: cause instanceof Error ? cause.message.slice(0, 500) : "unknown_error",
    });
    await saveState(key, state);
    throw Object.assign(
      cause instanceof Error ? cause : new Error(state.error),
      { orchestration: stateResult(state) },
    );
  }
}

export async function getActivePurchaseOrchestrations(
  cookieHeader: string,
): Promise<PurchaseOrchestrationState[]> {
  const index = activeIndex(cookieHeader);
  const keys = (await store().smembers(index)) as string[];
  const states = await Promise.all(
    keys.slice(0, 100).map(async (key) => {
      const state = await store().get<PurchaseOrchestrationState>(key);
      if (!state) {
        await store().srem(index, key);
        return null;
      }
      return stateResult(state);
    }),
  );
  return states
    .filter((state): state is PurchaseOrchestrationState => state !== null)
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
    .slice(0, 50);
}

async function continueStartedOrchestration(
  cookieHeader: string,
  idempotencyKey: string,
  key: string,
  state: PurchaseOrchestrationState,
): Promise<PurchaseOrchestrationState> {
  const existingMr = await findByCorrelation(
    "/api/v1/stock/material-requests",
    cookieHeader,
    state.id,
  );
  if (existingMr) {
    state.material_request_name = String(existingMr.name ?? "");
    const existingRfq = await findByCorrelation(
      "/api/v1/crm/request-for-quotations",
      cookieHeader,
      state.id,
    );
    const existingItems = await hydrateRfqItems(
      itemsFromCreatedMaterialRequest(existingMr),
      (itemCode) => validatedGatewayRequest<Row>(
        `/api/v1/stock/items/${encodeURIComponent(itemCode)}`,
        ItemResponseSchema,
        cookieHeader,
      ),
    );
    state.rfq_payload = buildRfqPayload(
      state.material_request,
      state.suppliers,
      existingItems,
      state.id,
    );
    state.status = "mr_created";
    if (existingRfq) {
      state.request_for_quotation_name = String(existingRfq.name ?? "");
      await issueSupplierPortalAccesses(state, existingMr);
    } else {
      const rfq = await validatedGatewayRequest<Row>(
        "/api/v1/crm/request-for-quotations",
        RequestforQuotationResponseSchema,
        cookieHeader,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Idempotency-Key": `${idempotencyKey}:rfq`,
          },
          body: JSON.stringify(state.rfq_payload),
        },
      );
      state.request_for_quotation_name = String(rfq.name ?? "");
      await issueSupplierPortalAccesses(state, existingMr);
    }
    state.status = "waiting_supplier_quotes";
    await saveState(key, state);
    return stateResult(state);
  }
  const stateItems = Array.isArray(state.material_request.items)
    ? state.material_request.items as Item[]
    : [];
  try {
    const materialRequestPayload = MaterialRequestWriteSchema.parse({
      ...state.material_request,
      items: stateItems.map(({ stock_uom, ...item }: Item) => {
        void stock_uom;
        return item;
      }),
      naming_series: "MR-.YYYYMMDD.-.####",
      custom_letron_orchestration_id: state.id,
    });
    const materialRequest = await validatedGatewayRequest<Row>(
      "/api/v1/stock/material-requests",
      MaterialRequestResponseSchema,
      cookieHeader,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Idempotency-Key": `${idempotencyKey}:mr`,
        },
        body: JSON.stringify(materialRequestPayload),
      },
    );
    state.material_request_name = String(materialRequest.name ?? "");
    state.rfq_payload = buildRfqPayload(
      state.material_request,
      state.suppliers,
      await hydrateRfqItems(
        itemsFromCreatedMaterialRequest(materialRequest),
        (itemCode) => validatedGatewayRequest<Row>(
          `/api/v1/stock/items/${encodeURIComponent(itemCode)}`,
          ItemResponseSchema,
          cookieHeader,
        ),
      ),
      state.id,
    );
    state.status = "mr_created";
    await saveState(key, state);
    const rfq = await validatedGatewayRequest<Row>(
      "/api/v1/crm/request-for-quotations",
      RequestforQuotationResponseSchema,
      cookieHeader,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Idempotency-Key": `${idempotencyKey}:rfq`,
        },
        body: JSON.stringify(state.rfq_payload),
      },
    );
    state.request_for_quotation_name = String(rfq.name ?? "");
    await issueSupplierPortalAccesses(state, materialRequest);
    state.status = "waiting_supplier_quotes";
    await saveState(key, state);
    return stateResult(state);
  } catch (cause) {
    state.status = "failed";
    state.error = errorMessage(cause);
    await saveState(key, state);
    throw Object.assign(cause instanceof Error ? cause : new Error(state.error), {
      orchestration: stateResult(state),
    });
  }
}

export async function getPurchaseOrchestration(
  cookieHeader: string,
  idempotencyKey: string,
): Promise<PurchaseOrchestrationState | null> {
  const state = await store().get<PurchaseOrchestrationState>(
    stateKey(cookieHeader, idempotencyKey),
  );
  return state ? stateResult(state) : null;
}

async function keyForOrchestrationId(
  cookieHeader: string,
  id: string,
): Promise<string | null> {
  const idempotencyKey = await store().get<string>(idKey(cookieHeader, id));
  return idempotencyKey ? stateKey(cookieHeader, idempotencyKey) : null;
}

export async function getPurchaseOrchestrationById(
  cookieHeader: string,
  id: string,
): Promise<PurchaseOrchestrationState | null> {
  const key = await keyForOrchestrationId(cookieHeader, id);
  if (!key) return null;
  const state = await store().get<PurchaseOrchestrationState>(key);
  return state ? stateResult(state) : null;
}

export async function retryPurchaseRfq(
  cookieHeader: string,
  idempotencyKey: string,
): Promise<PurchaseOrchestrationState> {
  const key = stateKey(cookieHeader, idempotencyKey);
  const state = await store().get<PurchaseOrchestrationState>(key);
  if (!state)
    throw new PurchaseOrchestrationValidationError(
      "Orchestration state was not found or has expired.",
    );
  if (state.status === "waiting_supplier_quotes") return stateResult(state);
  if (!state.material_request_name)
    throw new PurchaseOrchestrationValidationError(
      "Material Request was not created; RFQ cannot be retried.",
    );
  const stateItems = Array.isArray(state.material_request.items)
    ? state.material_request.items as Item[]
    : [];
  const materialRequest = await gatewayRequest<Row>(
    `/api/v1/stock/material-requests/${encodeURIComponent(state.material_request_name)}`,
    cookieHeader,
  );
  const lock = await store().set(retryKey(key), "locked", { nx: true, ex: 90 });
  if (!lock) return stateResult(state);
  try {
    const existingRfq = await findByCorrelation(
      "/api/v1/crm/request-for-quotations",
      cookieHeader,
      state.id,
    );
    if (existingRfq) {
    state.request_for_quotation_name = String(existingRfq.name ?? "");
      await issueSupplierPortalAccesses(state, materialRequest);
      state.status = "waiting_supplier_quotes";
      state.retry_count += 1;
      await saveState(key, state);
      return stateResult(state);
    }
    const rfq = await validatedGatewayRequest<Row>(
      "/api/v1/crm/request-for-quotations",
      RequestforQuotationResponseSchema,
      cookieHeader,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Idempotency-Key": `${idempotencyKey}:rfq`,
        },
        body: JSON.stringify(state.rfq_payload),
      },
    );
    state.request_for_quotation_name = String(rfq.name ?? "");
    await issueSupplierPortalAccesses(state, materialRequest);
    state.status = "waiting_supplier_quotes";
    state.retry_count += 1;
    await saveState(key, state);
    return stateResult(state);
  } catch (cause) {
    state.status = "partial_failure";
    state.error = errorMessage(cause);
    state.retry_count += 1;
    await saveState(key, state);
    throw Object.assign(
      cause instanceof Error ? cause : new Error(state.error),
      { orchestration: stateResult(state) },
    );
  } finally {
    await store().del(retryKey(key));
  }
}

export async function retryPurchaseRfqById(
  cookieHeader: string,
  id: string,
): Promise<PurchaseOrchestrationState> {
  const idempotencyKey = await store().get<string>(idKey(cookieHeader, id));
  if (!idempotencyKey)
    throw new PurchaseOrchestrationValidationError(
      "Orchestration state was not found or has expired.",
    );
  return retryPurchaseRfq(cookieHeader, idempotencyKey);
}
