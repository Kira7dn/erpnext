import "server-only";

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export type BankAccount = {
  name: string;
  account_name?: string;
  account?: string;
  bank?: string;
  company?: string;
  currency?: string;
  disabled?: boolean;
  is_default?: boolean;
  account_type?: string;
  bank_account_no?: string;
};

type ApiResponse<T> = { data?: T; message?: unknown };

export type AccountingResource =
  | "banks"
  | "bank-accounts"
  | "bank-transactions"
  | "cost-centers"
  | "journal-entries"
  | "modes-of-payment"
  | "payment-entries"
  | "payment-orders"
  | "payment-requests"
  | "purchase-invoices"
  | "sales-invoices"
  | "bank-transaction-rules";

export type AccountingVirtualResource = "bank-reconciliation" | "reports" | "statement-imports" | "settings";

export type AssetResource = "assets" | "asset-categories" | "asset-capitalizations" | "asset-maintenance" | "asset-movements" | "asset-repairs" | "asset-value-adjustments" | "asset-maintenance-teams" | "asset-maintenance-logs" | "asset-depreciation-schedules" | "asset-shift-factors" | "asset-shift-allocations" | "locations";
export type AssetVirtualResource = "actions" | "reports" | "dashboard";
export type AssetReportKey = "fixed-asset-register" | "asset-depreciation-ledger" | "asset-depreciations-and-balances" | "asset-maintenance" | "asset-activity";

export const ACCOUNTING_RESOURCES = [
  "banks",
  "bank-accounts",
  "bank-transactions",
  "cost-centers",
  "journal-entries",
  "modes-of-payment",
  "payment-entries",
  "payment-orders",
  "payment-requests",
  "purchase-invoices",
  "sales-invoices",
  "bank-transaction-rules",
] as const satisfies readonly AccountingResource[];

export const ACCOUNTING_VIRTUAL_RESOURCES = ["bank-reconciliation", "reports", "statement-imports", "settings"] as const satisfies readonly AccountingVirtualResource[];
export const ASSET_RESOURCES = ["assets", "asset-categories", "asset-capitalizations", "asset-maintenance", "asset-movements", "asset-repairs", "asset-value-adjustments", "asset-maintenance-teams", "asset-maintenance-logs", "asset-depreciation-schedules", "asset-shift-factors", "asset-shift-allocations", "locations"] as const satisfies readonly AssetResource[];
export const ASSET_VIRTUAL_RESOURCES = ["actions", "reports", "dashboard"] as const satisfies readonly AssetVirtualResource[];
export const ASSET_REPORTS = ["fixed-asset-register", "asset-depreciation-ledger", "asset-depreciations-and-balances", "asset-maintenance", "asset-activity"] as const satisfies readonly AssetReportKey[];

export type AccountingFormField = {
  name: string;
  type: "string" | "number" | "integer" | "boolean" | "array";
  format?: string;
  enum?: string[];
  required: boolean;
  targetDoctype?: string;
};

export const RESOURCE_PAGE_SIZE = 25;

export function resourcePageQuery(page: number, pageSize = RESOURCE_PAGE_SIZE): string {
  const safePage = Math.max(1, Math.floor(page));
  return new URLSearchParams({
    limit_page_length: String(pageSize + 1),
    limit_start: String((safePage - 1) * pageSize),
  }).toString();
}

type ContractSchema = { properties?: Record<string, { type?: string; format?: string; enum?: string[]; writeOnly?: boolean; "x-frappe-target-doctype"?: string }> ; required?: string[] };
type PublicContract = { paths?: Record<string, Record<string, { requestBody?: { content?: { "application/json"?: { schema?: ContractSchema } } } }>> };

let contract: PublicContract | undefined;
function readContract(): PublicContract {
  contract ??= JSON.parse(readFileSync(resolve(process.cwd(), "../../contracts/openapi/public.json"), "utf8")) as PublicContract;
  return contract;
}

export function getAccountingFormFields(resource: AccountingResource): AccountingFormField[] {
  const schema = readContract().paths?.[`/api/v1/accounts/${resource}`]?.post?.requestBody?.content?.["application/json"]?.schema;
  if (!schema?.properties) return [];
  const required = new Set(schema.required ?? []);
  return Object.entries(schema.properties)
    .filter(([name, field]) => !/^(section|column|sb|cb|address_and_contact|integration_details|.*_section|.*_tab|.*_html|printing_settings|more_info|connections_tab|automation_section|totals_section|base_totals_section|title$)/i.test(name) && !field.writeOnly)
    .map(([name, field]) => ({
      name,
      type: ["string", "number", "integer", "boolean", "array"].includes(field.type ?? "") ? field.type as AccountingFormField["type"] : "string",
      format: field.format,
      enum: field.enum,
      required: required.has(name),
      targetDoctype: field["x-frappe-target-doctype"],
    }));
}

export class GatewayAuthenticationRequiredError extends Error {
  constructor() {
    super("Bạn cần đăng nhập qua Letron Global Portal.");
    this.name = "GatewayAuthenticationRequiredError";
  }
}

export class GatewayAccessDeniedError extends Error {
  constructor() {
    super("Tài khoản hiện tại chưa được cấp quyền cho phân hệ này.");
    this.name = "GatewayAccessDeniedError";
  }
}

export class GatewayUnavailableError extends Error {
  constructor() {
    super("Letron Global Portal Gateway hiện không khả dụng. Vui lòng thử lại sau.");
    this.name = "GatewayUnavailableError";
  }
}

function authGatewayUrl(path: string): string {
  const baseUrl = (process.env.LETRON_AUTH_BASE_URL ?? "http://localhost:3000").replace(/\/$/, "");
  return `${baseUrl}/api/gateway${path}`;
}

export function isAccountingResource(value: string): value is AccountingResource {
  return [...ACCOUNTING_RESOURCES, ...ACCOUNTING_VIRTUAL_RESOURCES].includes(value as AccountingResource | AccountingVirtualResource);
}

export function isAccountingVirtualResource(value: string): value is AccountingVirtualResource {
  return (ACCOUNTING_VIRTUAL_RESOURCES as readonly string[]).includes(value);
}

export function isAssetResource(value: string): value is AssetResource {
  return (ASSET_RESOURCES as readonly string[]).includes(value);
}

export function isAssetVirtualResource(value: string): value is AssetVirtualResource {
  return (ASSET_VIRTUAL_RESOURCES as readonly string[]).includes(value);
}

export function assetsGatewayRequest<T>(path: string, cookieHeader: string, init: RequestInit = {}): Promise<T> {
  return gatewayRequest<T>(`/api/v1/assets/${path.replace(/^\/+/, "")}`, cookieHeader, init);
}

export async function listAssetResource(resource: AssetResource, cookieHeader: string, searchParams = ""): Promise<Record<string, unknown>[]> {
  const suffix = searchParams ? `?${searchParams}` : "";
  const data = await assetsGatewayRequest<unknown>(`${resource}${suffix}`, cookieHeader);
  return Array.isArray(data) ? data as Record<string, unknown>[] : [];
}

export function getAssetFormFields(resource: AssetResource): AccountingFormField[] {
  const schema = readContract().paths?.[`/api/v1/assets/${resource}`]?.post?.requestBody?.content?.["application/json"]?.schema;
  if (!schema?.properties) return [];
  const required = new Set(schema.required ?? []);
  return Object.entries(schema.properties)
    .filter(([name, field]) => !/^(section|column|sb|cb|.*_section|.*_tab|.*_html|title$)/i.test(name) && !field.writeOnly)
    .map(([name, field]) => ({ name, type: ["string", "number", "integer", "boolean", "array"].includes(field.type ?? "") ? field.type as AccountingFormField["type"] : "string", format: field.format, enum: field.enum, required: required.has(name), targetDoctype: field["x-frappe-target-doctype"] }));
}

export async function accountingGatewayRequest<T>(path: string, cookieHeader: string, init: RequestInit = {}): Promise<T> {
  return gatewayRequest<T>(`/api/v1/accounts/${path.replace(/^\/+/, "")}`, cookieHeader, init);
}

export async function gatewayRequest<T>(
  path: string,
  cookieHeader: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (cookieHeader) headers.set("Cookie", cookieHeader);
  let response: Response;
  try {
    response = await fetch(authGatewayUrl(path), {
      ...init,
      headers,
      cache: "no-store",
    });
  } catch {
    throw new GatewayUnavailableError();
  }
  if (response.status === 401) throw new GatewayAuthenticationRequiredError();
  if (response.status === 403) throw new GatewayAccessDeniedError();
  if (response.status === 502 || response.status === 503) throw new GatewayUnavailableError();
  if (!response.ok) {
    throw new Error(`Letron Gateway request failed (${response.status}).`);
  }
  const payload = await response.json() as ApiResponse<T>;
  return (payload.data ?? payload.message) as T;
}

export async function listAccountingResource(
  resource: AccountingResource,
  cookieHeader: string,
  searchParams = "",
): Promise<Record<string, unknown>[]> {
  const suffix = searchParams ? `?${searchParams}` : "";
  const data = await gatewayRequest<unknown>(`/api/v1/accounts/${resource}${suffix}`, cookieHeader);
  return Array.isArray(data) ? data as Record<string, unknown>[] : [];
}

export async function getAccountingResource(
  resource: AccountingResource,
  name: string,
  cookieHeader: string,
): Promise<Record<string, unknown>> {
  return gatewayRequest<Record<string, unknown>>(
    `/api/v1/accounts/${resource}/${encodeURIComponent(name)}`,
    cookieHeader,
  );
}

export async function listBankAccounts(cookieHeader: string, searchParams = ""): Promise<BankAccount[]> {
  return listAccountingResource("bank-accounts", cookieHeader, searchParams) as Promise<BankAccount[]>;
}
