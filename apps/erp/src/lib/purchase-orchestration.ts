import "server-only";

import { createHash } from "node:crypto";
import { Redis } from "@upstash/redis";
import {
  GatewayAccessDeniedError,
  GatewayAuthenticationRequiredError,
  GatewayUnavailableError,
  gatewayRequest,
} from "@/lib/letron-api";
import { portalAuthBaseUrl } from "@/lib/portal-config";

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
  supplier_quotation_name?: string;
  justification?: string;
};
export type PurchaseOrchestrationState = {
  id: string;
  status: "started" | "mr_created" | "partial_failure" | "rfq_created" | "approval_pending" | "approval_failed" | "completed" | "failed";
  material_request: Row;
  suppliers: string[];
  rfq_payload: Row;
  material_request_name?: string;
  request_for_quotation_name?: string;
  supplier_quotation_name?: string;
  justification?: string;
  lark_po?: Record<string, unknown>;
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
    throw new Error("ERP orchestration Redis is not configured.");
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

function buildRfqPayload(
  materialRequest: Row,
  suppliers: string[],
  items: Item[],
  orchestrationId?: string,
): Row {
  return {
    naming_series: "RFQ-.YYYY.-",
    company: materialRequest.company,
    transaction_date: materialRequest.transaction_date,
    subject: materialRequest.title || "RFQ from Material Request",
    status: "Draft",
    suppliers: suppliers.map((supplier) => ({ supplier })),
    items: items.map(({ name: _name, rate: _rate, ...item }) => item),
    ...(orchestrationId
      ? { custom_letron_orchestration_id: orchestrationId }
      : {}),
  };
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

function itemsFromCreatedMaterialRequest(
  materialRequest: Row,
  fallback: Item[],
): Item[] {
  if (!Array.isArray(materialRequest.items) || !materialRequest.items.length) {
    return fallback;
  }
  return materialRequest.items.map((item, index) => {
    const source = item as Row;
    const original = fallback[index] ?? fallback[0];
    return {
      item_code: String(source.item_code ?? original.item_code),
      qty: Number(source.qty ?? original.qty),
      schedule_date:
        String(source.schedule_date ?? original.schedule_date ?? "").trim() ||
        undefined,
      warehouse:
        String(source.warehouse ?? original.warehouse ?? "").trim() ||
        undefined,
      uom: String(source.uom ?? original.uom ?? "").trim() || undefined,
      stock_uom:
        String(source.stock_uom ?? original.stock_uom ?? "").trim() ||
        undefined,
      conversion_factor:
        Number(source.conversion_factor ?? original.conversion_factor) || 1,
      rate: Number(source.rate ?? source.price_list_rate ?? original.rate) || 0,
      name: String(source.name ?? original.name ?? "").trim() || undefined,
      material_request: String(source.material_request ?? materialRequest.name ?? "").trim() || undefined,
      material_request_item: String(source.material_request_item ?? source.name ?? "").trim() || undefined,
    };
  });
}

async function saveState(
  key: string,
  state: PurchaseOrchestrationState,
): Promise<void> {
  state.updated_at = new Date().toISOString();
  await store().set(key, state, { ex: STATE_TTL_SECONDS });
  const owner = key.slice(PREFIX.length).split(":")[0];
  const index = `${PREFIX}active:${owner}`;
  if (state.status === "completed") await store().srem(index, key);
  else await store().sadd(index, key);
}

function stateResult(
  state: PurchaseOrchestrationState,
): PurchaseOrchestrationState {
  return structuredClone(state);
}

function errorMessage(cause: unknown): string {
  return cause instanceof Error ? cause.message : "ERP request failed.";
}

async function submitLarkApproval(
  cookieHeader: string,
  orchestrationId: string,
  justification?: string,
): Promise<Record<string, unknown>> {
  const response = await fetch(
    `${portalAuthBaseUrl()}/api/integrations/lark/purchase-orchestrations/${encodeURIComponent(orchestrationId)}/submit-approval`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...( /^Bearer\s+\S+$/i.test(cookieHeader)
          ? { Authorization: cookieHeader }
          : { Cookie: cookieHeader }),
      },
      body: JSON.stringify({ justification }),
      cache: "no-store",
      signal: AbortSignal.timeout(60_000),
    },
  );
  const payload = (await response.json().catch(() => ({}))) as { data?: Record<string, unknown>; error?: unknown };
  if (!response.ok) {
    const detail = typeof payload.error === "string" ? payload.error : `Lark approval failed (${response.status}).`;
    throw new Error(detail);
  }
  return (payload.data ?? payload) as Record<string, unknown>;
}

async function finishLarkApproval(
  cookieHeader: string,
  state: PurchaseOrchestrationState,
): Promise<void> {
  try {
    state.lark_po = await submitLarkApproval(
      cookieHeader,
      state.id,
      state.justification,
    );
    state.status = "approval_pending";
    state.error = undefined;
  } catch (cause) {
    state.status = "approval_failed";
    state.error = errorMessage(cause);
  }
}

export function orchestrationHttpStatus(cause: unknown): number {
  if (cause instanceof PurchaseOrchestrationValidationError) return 400;
  if (cause instanceof GatewayAuthenticationRequiredError) return 401;
  if (cause instanceof GatewayAccessDeniedError) return 403;
  if (cause instanceof GatewayUnavailableError) return 503;
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
    supplier_quotation_name: String(input.supplier_quotation_name ?? "").trim() || undefined,
    justification: String(input.justification ?? "").trim() || undefined,
    rfq_payload: buildRfqPayload(
      normalized.materialRequest,
      normalized.suppliers,
      normalized.items,
      correlationId(idempotencyKey),
    ),
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
    throw new Error("Could not claim orchestration state.");
  }
  await store().sadd(activeIndex(cookieHeader), key);
  await store().set(idKey(cookieHeader, state.id), idempotencyKey, {
    ex: STATE_TTL_SECONDS,
  });
  try {
    state.rfq_payload = buildRfqPayload(
      normalized.materialRequest,
      normalized.suppliers,
      normalized.items,
      state.id,
    );
    const materialRequest = await gatewayRequest<Row>(
      "/api/v1/stock/material-requests",
      cookieHeader,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Idempotency-Key": `${idempotencyKey}:mr`,
        },
        body: JSON.stringify({
          ...normalized.materialRequest,
          custom_letron_orchestration_id: state.id,
        }),
      },
    );
    state.material_request_name = String(materialRequest.name ?? "");
    state.rfq_payload = buildRfqPayload(
      normalized.materialRequest,
      normalized.suppliers,
      itemsFromCreatedMaterialRequest(materialRequest, normalized.items),
      state.id,
    );
    state.status = "mr_created";
    await saveState(key, state);
    const rfq = await gatewayRequest<Row>(
      "/api/v1/crm/request-for-quotations",
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
    await finishLarkApproval(cookieHeader, state);
    await saveState(key, state);
    return stateResult(state);
  } catch (cause) {
    const hasMr = Boolean(state.material_request_name);
    state.status = hasMr ? "partial_failure" : "failed";
    state.error = errorMessage(cause);
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
      if (state.status === "completed") {
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
    const fallbackItems = Array.isArray(state.material_request.items)
      ? (state.material_request.items as Item[])
      : [];
    state.material_request_name = String(existingMr.name ?? "");
    const existingRfq = await findByCorrelation(
      "/api/v1/crm/request-for-quotations",
      cookieHeader,
      state.id,
    );
    const existingItems = itemsFromCreatedMaterialRequest(existingMr, fallbackItems);
    state.rfq_payload = buildRfqPayload(
      state.material_request,
      state.suppliers,
      existingItems,
      state.id,
    );
    state.status = "mr_created";
    if (existingRfq) {
      state.request_for_quotation_name = String(existingRfq.name ?? "");
    } else {
      const rfq = await gatewayRequest<Row>(
        "/api/v1/crm/request-for-quotations",
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
    }
    await finishLarkApproval(cookieHeader, state);
    await saveState(key, state);
    return stateResult(state);
  }
  try {
    const materialRequest = await gatewayRequest<Row>(
      "/api/v1/stock/material-requests",
      cookieHeader,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Idempotency-Key": `${idempotencyKey}:mr`,
        },
        body: JSON.stringify({
          ...state.material_request,
          custom_letron_orchestration_id: state.id,
        }),
      },
    );
    state.material_request_name = String(materialRequest.name ?? "");
    state.rfq_payload = buildRfqPayload(
      state.material_request,
      state.suppliers,
      itemsFromCreatedMaterialRequest(
        materialRequest,
        Array.isArray(state.material_request.items)
          ? (state.material_request.items as Item[])
          : [],
      ),
      state.id,
    );
    state.status = "mr_created";
    await saveState(key, state);
    const rfq = await gatewayRequest<Row>(
      "/api/v1/crm/request-for-quotations",
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
    await finishLarkApproval(cookieHeader, state);
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
  if (state.status === "completed" || state.status === "approval_pending") return stateResult(state);
  if (!state.material_request_name)
    throw new PurchaseOrchestrationValidationError(
      "Material Request was not created; RFQ cannot be retried.",
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
      await finishLarkApproval(cookieHeader, state);
      state.retry_count += 1;
      await saveState(key, state);
      return stateResult(state);
    }
    const rfq = await gatewayRequest<Row>(
      "/api/v1/crm/request-for-quotations",
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
    await finishLarkApproval(cookieHeader, state);
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

export async function submitLarkApprovalById(
  cookieHeader: string,
  id: string,
  supplierQuotationName = "",
  justification?: string,
): Promise<PurchaseOrchestrationState> {
  const key = await keyForOrchestrationId(cookieHeader, id);
  if (!key)
    throw new PurchaseOrchestrationValidationError(
      "Orchestration state was not found or has expired.",
    );
  const state = await store().get<PurchaseOrchestrationState>(key);
  if (!state)
    throw new PurchaseOrchestrationValidationError(
      "Orchestration state was not found or has expired.",
    );
  if (!state.request_for_quotation_name)
    throw new PurchaseOrchestrationValidationError(
      "RFQ must be created before Lark approval can be submitted.",
    );
  state.supplier_quotation_name = supplierQuotationName.trim() || undefined;
  state.justification = justification?.trim() || state.justification;
  try {
    state.lark_po = await submitLarkApproval(
      cookieHeader,
      state.id,
      state.justification,
    );
    state.status = "approval_pending";
    state.error = undefined;
    await saveState(key, state);
    return stateResult(state);
  } catch (cause) {
    state.status = "approval_failed";
    state.error = errorMessage(cause);
    await saveState(key, state);
    throw Object.assign(cause instanceof Error ? cause : new Error(state.error), {
      orchestration: stateResult(state),
    });
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
