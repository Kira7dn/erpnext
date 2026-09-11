import { createHmac, randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";

function env(name: string): string {
  const value = process.env[name]?.trim();
  if (value) return value;
  try {
    const line = readFileSync(".env", "utf8")
      .split(/\r?\n/)
      .find((item) => item.startsWith(`${name}=`));
    return line?.slice(name.length + 1).trim().replace(/^['"]|['"]$/g, "") ?? "";
  } catch {
    return "";
  }
}

const baseUrl = (env("FRAPPE_ERP_NEXT_URL") || "http://localhost:8080").replace(/\/$/, "");
const path = "/api/v1/crm/supplier-quotations";
const secret = env("LETRON_INTERNAL_API_SECRET");
if (!secret) throw new Error("LETRON_INTERNAL_API_SECRET is missing");

const body = {
  doctype: "Supplier Quotation",
  naming_series: "SQ-.YYYYMMDD.-.####",
  supplier: "Link Strategy",
  company: "Letron Việt Nam",
  transaction_date: new Date().toISOString().slice(0, 10),
  custom_letron_orchestration_id: `DIRECT-API-${Date.now()}`,
  items: [
    {
      item_code: "ACCEPTANCE-LOCAL-f7aa6b9e-Item",
      qty: 2,
      uom: "Nos",
      warehouse: "Cửa hàng - LTVN",
      rate: 1000,
      expected_delivery_date: "2026-10-10",
      request_for_quotation: "RFQ-20260910-0087",
      request_for_quotation_item: "2j8o5tjfns",
      material_request: "MR-20260910-0087",
      material_request_item: "2j45slk21u",
    },
    {
      item_code: "ACCEPTANCE-LOCAL-8cee0a8e-Purchase Flow Item",
      qty: 3,
      uom: "Nos",
      warehouse: "Cửa hàng - LTVN",
      rate: 2000,
      expected_delivery_date: "2026-10-10",
      request_for_quotation: "RFQ-20260910-0087",
      request_for_quotation_item: "2j88fm19hu",
      material_request: "MR-20260910-0087",
      material_request_item: "2j4utv6oom",
    },
  ],
};

const method = "POST";
const timestamp = Math.floor(Date.now() / 1000);
const expires = timestamp + 60;
const requestId = randomUUID();
const payload = `${timestamp}.${expires}.${method}.${path}.${requestId}`;
const signature = createHmac("sha256", secret).update(payload).digest("hex");

const requestHeaders = {
  Accept: "application/json",
  "Content-Type": "application/json",
  "X-Letron-Control-Timestamp": String(timestamp),
  "X-Letron-Control-Expires-At": String(expires),
  "X-Letron-Control-Request-Id": requestId,
  "X-Letron-Control-Signature": signature,
};
console.log("=== LETRON API QUOTATION TEST ===");
console.log("REQUEST METHOD:", method);
console.log("REQUEST URL:", `${baseUrl}${path}`);
console.log("REQUEST HEADERS:", JSON.stringify({ ...requestHeaders, "X-Letron-Control-Signature": "<redacted>" }, null, 2));
console.log("REQUEST BODY:", JSON.stringify(body, null, 2));

void (async () => {
try {
  const response = await fetch(`${baseUrl}${path}`, { method, headers: requestHeaders, body: JSON.stringify(body) });
  const raw = await response.text();
  console.log("RESPONSE STATUS:", response.status, response.statusText);
  console.log("RESPONSE HEADERS:", JSON.stringify(Object.fromEntries(response.headers.entries()), null, 2));
  console.log("RESPONSE BODY:", raw || "<empty>");
  console.log("RESULT:", response.ok ? "PASS" : "FAIL");
  if (!response.ok) process.exitCode = 1;
} catch (error) {
  console.error("REQUEST ERROR:", error instanceof Error ? error.stack ?? error.message : error);
  process.exitCode = 1;
}
})();
