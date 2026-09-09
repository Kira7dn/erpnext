import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

type Json = Record<string, unknown> | unknown[] | string | number | boolean | null;

const root = resolve(import.meta.dirname, "..");
const erpBaseUrl = process.env.ERP_BASE_URL ?? "http://localhost:3001";
const portalBaseUrl = process.env.PORTAL_BASE_URL ?? "http://localhost:3000";
const item1 = process.env.MR_ITEM_1 ?? "ACCEPTANCE-LOCAL-f7aa6b9e-Item";
const item2 = process.env.MR_ITEM_2 ?? "ACCEPTANCE-LOCAL-f7aa6b9e-Trace Item";
const supplier1 = process.env.MR_SUPPLIER_1 ?? "ACCEPTANCE-LOCAL-f7aa6b9e-Supplier";
const supplier2 = process.env.MR_SUPPLIER_2 ?? "dsfsdfsdfd";
const idempotencyKey = process.env.MR_IDEMPOTENCY_KEY ?? `real-mr-approval-${Date.now()}`;

function object(value: Json): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function data(value: Json): Json {
  const row = object(value);
  return row.data ?? row.message ?? value;
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
      ...(init.body ? { "Content-Type": "application/json; charset=utf-8" } : {}),
      ...init.headers,
    },
  });
  const raw = await response.text();
  let body: Json = null;
  try { body = raw ? JSON.parse(raw) as Json : null; } catch { body = raw; }
  return { status: response.status, body, raw, cookie: response.headers.get("set-cookie")?.split(";", 1)[0] ?? "" };
}

async function main(): Promise<void> {
const apiKey = await env("LETRON_API_KEY");
const apiAuth = { Authorization: `Bearer ${apiKey}` };

const session = await request(`${portalBaseUrl}/api/internal/test-session`, {
  method: "POST",
  headers: apiAuth,
});
if (session.status !== 200) throw new Error(`test-session failed (${session.status}): ${session.raw}`);
if (!session.cookie) throw new Error("test-session did not return a session cookie");
const auth = { Cookie: session.cookie };

const seedList = await request(`${erpBaseUrl}/api/purchase/material-requests?limit_page_length=1&order_by=creation%20desc`, { headers: auth });
if (seedList.status !== 200) throw new Error(`cannot read seed MR (${seedList.status}): ${seedList.raw}`);
const seedValue = data(seedList.body);
const seed = object(Array.isArray(seedValue) ? (seedValue[0] as Json) : seedValue);
const seedName = text(seed.name);
if (!seedName) throw new Error("no existing Material Request available");

const seedDetail = await request(`${erpBaseUrl}/api/purchase/material-requests/${encodeURIComponent(seedName)}`, { headers: auth });
if (seedDetail.status !== 200) throw new Error(`cannot read seed MR ${seedName} (${seedDetail.status}): ${seedDetail.raw}`);
const seedRow = object(data(seedDetail.body));
const company = text(seedRow.company);
const items = Array.isArray(seedRow.items) ? seedRow.items : [];
const warehouse = text(items.map((row) => object(row as Json).warehouse).find(Boolean));
if (!company || !warehouse) throw new Error(`seed MR ${seedName} has no usable company/warehouse`);

const today = new Date();
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
  suppliers: [supplier1, supplier2],
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
const result = object(data(created.body));
const larkPo = object(result.lark_po as Json);
const mrName = text(result.material_request_name);
const rfqName = text(result.request_for_quotation_name);
const approvalInstance = text(larkPo.instanceCode || larkPo.instance_code);
if (!mrName || !approvalInstance) throw new Error(`orchestration did not return MR and Approval: ${created.raw}`);

const readback = await request(`${erpBaseUrl}/api/purchase/material-requests/${encodeURIComponent(mrName)}`, { headers: auth });
if (readback.status !== 200) throw new Error(`MR readback failed (${readback.status}): ${readback.raw}`);
const createdRow = object(data(readback.body));
const itemCount = Array.isArray(createdRow.items) ? createdRow.items.length : 0;
if (itemCount !== 2) throw new Error(`MR ${mrName} has ${itemCount} items; expected 2`);

console.log("REAL_MR_TEST=PASS");
console.log(`status=${text(result.status)}`);
console.log(`orchestration_id=${text(result.id)}`);
console.log(`material_request=${mrName}`);
console.log(`request_for_quotation=${rfqName}`);
console.log(`approval_instance=${approvalInstance}`);
console.log(`items=${itemCount}`);
console.log(`suppliers=${Array.isArray(result.suppliers) ? result.suppliers.length : 0}`);
console.log("approver=leducanh@ledb.vn");
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
