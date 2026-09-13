import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";

import type {
  AddressWrite,
  ContactWrite,
  MaterialRequestWrite,
  PurchaseOrderWrite,
  PurchaseReceiptWrite,
  RequestforQuotationWrite,
  SupplierQuotationWrite,
  SupplierWrite,
} from "../../apps/erp/src/generated/types";
import { GENERATED_OPERATION_CONTRACTS } from "../../apps/erp/src/generated/zod";

type Contract = (typeof GENERATED_OPERATION_CONTRACTS)[keyof typeof GENERATED_OPERATION_CONTRACTS];
type Json = Record<string, unknown>;

try {
  const envText = readFileSync(".env", "utf8");
  for (const line of envText.split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
    if (match && process.env[match[1]] === undefined) process.env[match[1]] = match[2].replace(/^['"]|['"]$/g, "");
  }
} catch { /* launcher may already provide the environment */ }

function configured(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

export const prefix = `FE-API-${randomUUID().slice(0, 8).toUpperCase()}`;
export const today = new Date().toISOString().slice(0, 10);
export const gatewayBaseUrl = `${configured("LETRON_AUTH_BASE_URL").replace(/\/$/, "")}/api/gateway`;

function contract(operation: string): Contract {
  const value = GENERATED_OPERATION_CONTRACTS[operation as keyof typeof GENERATED_OPERATION_CONTRACTS];
  if (!value) throw new Error(`generated operation missing: ${operation}`);
  return value;
}

function pathFor(template: string, name?: string): string {
  if (!name) return `${gatewayBaseUrl}${template}`;
  if (!template.includes("{name}")) return `${gatewayBaseUrl}${template}${name.startsWith("?") ? name : `?${name}`}`;
  return `${gatewayBaseUrl}${template.replace("{name}", encodeURIComponent(name))}`;
}

export async function call<T extends Json = Json>(
  operation: string,
  name?: string,
  payload?: unknown,
  init: RequestInit = {},
): Promise<T> {
  const selected = contract(operation);
  if (payload !== undefined && "request" in selected && selected.request) {
    selected.request.parse(payload);
  }
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${configured("LETRON_INTERNAL_API_SECRET")}`);
  if (payload !== undefined && !(payload instanceof FormData)) {
    headers.set("Content-Type", "application/json");
    init.body = JSON.stringify(payload);
  } else if (payload instanceof FormData) {
    init.body = payload;
  }
  const response = await fetch(pathFor(selected.path, name), { ...init, method: selected.method, headers });
  const raw = await response.text();
  let parsed: unknown = {};
  try { parsed = raw ? JSON.parse(raw) : {}; } catch { /* retain raw in error */ }
  if (!response.ok) throw new Error(`${operation} ${response.status}: ${raw.slice(0, 1000)}`);
  if ("response" in selected && selected.response) selected.response.parse(parsed);
  return parsed as T;
}

export function data<T extends Json = Json>(response: T): Json {
  const value = response.data ?? response.message;
  return (value && typeof value === "object" ? value : response) as Json;
}

export function assertName(response: Json, expected?: string): string {
  const name = typeof response.name === "string" ? response.name : "";
  if (!name || (expected && name !== expected)) throw new Error(`unexpected document name: ${JSON.stringify(response)}`);
  return name;
}

export function assertSubmitted(response: Json, expected: string): void {
  const row = data(response);
  assertName(row, expected);
  if (Number(row.docstatus) !== 1) throw new Error(`document ${expected} was not submitted: ${JSON.stringify(row)}`);
}

export function asWrite<T>(value: T): T { return value; }
export type { AddressWrite, ContactWrite, MaterialRequestWrite, PurchaseOrderWrite, PurchaseReceiptWrite, RequestforQuotationWrite, SupplierQuotationWrite, SupplierWrite };
