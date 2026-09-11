import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorFromResponse, apiErrorResponse } from "@/lib/api-error";
import { isPurchaseResource } from "@/lib/letron-api";
import { portalAuthBaseUrl } from "@/lib/portal-config";
import { APP_SESSION_COOKIES } from "@/lib/erp-auth-session";
import { notifySupplierInvoiceRequest } from "@/lib/supplier-portal";

const METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);
const OFFICIAL_MODULES: Record<string, string> = {
  suppliers: "buying/suppliers",
  contacts: "contacts/contacts",
  addresses: "contacts/addresses",
  items: "stock/items",
  "material-requests": "stock/material-requests",
  "request-for-quotations": "crm/request-for-quotations",
  "purchase-orders": "buying/purchase-orders",
  "purchase-receipts": "stock/purchase-receipts",
  attachments: "files/attachments",
};
export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxy(request, context);
}
export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxy(request, context);
}
export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxy(request, context);
}
export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxy(request, context);
}
export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxy(request, context);
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const startedAt = performance.now();
  if (!METHODS.has(request.method))
    return apiErrorResponse("method_not_allowed", 405, "Method is not allowed.");
  const { path } = await context.params;
  if (!path?.length || !isPurchaseResource(path[0]))
    return apiErrorResponse("unknown_purchase_resource", 404, "Purchase resource was not found.");
  const officialPath = `${OFFICIAL_MODULES[path[0]]}${path
    .slice(1)
    .map((part) => `/${encodeURIComponent(part)}`)
    .join("")}`;
  const target = `${portalAuthBaseUrl()}/api/gateway/api/v1/${officialPath}${request.nextUrl.search}`;
  const headers = new Headers({ Accept: "application/json" });
  const sessionCookie = (await cookies()).get(APP_SESSION_COOKIES.purchase)?.value;
  if (sessionCookie) { headers.set("X-Letron-App-Session", sessionCookie); headers.set("X-Letron-App", "purchase"); }
  const authorization = request.headers.get("authorization");
  if (authorization) headers.set("Authorization", authorization);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  let response: Response;
  try {
    response = await fetch(target, {
      method: request.method,
      headers,
      body:
        request.method === "GET" || request.method === "DELETE"
          ? undefined
          : await request.arrayBuffer(),
      cache: "no-store",
    });
  } catch {
    return apiErrorResponse("gateway_unavailable", 503, "Letron Gateway is unavailable.", true);
  }
  if (!response.ok)
    return apiErrorFromResponse(response, "purchase_request_failed");
  if (path[0] === "purchase-receipts" && path.at(-1) === "submit" && path.length === 3) {
    try {
      await notifySupplierInvoiceRequest(decodeURIComponent(path[1]));
    } catch (error) {
      return apiErrorFromCause(error, "invoice_request_failed", "Purchase Receipt was submitted but the supplier invoice request could not be sent.");
    }
  }
  const responseHeaders = new Headers({
    "content-type": response.headers.get("content-type") ?? "application/json",
  });
  const timing = response.headers.get("server-timing");
  if (timing)
    responseHeaders.set(
      "Server-Timing",
      `${timing}, erp_purchase_route;dur=${(performance.now() - startedAt).toFixed(1)}`,
    );
  return new NextResponse(response.body, {
    status: response.status,
    headers: responseHeaders,
  });
}
