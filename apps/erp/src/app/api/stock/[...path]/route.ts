import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { apiErrorFromResponse, apiErrorResponse } from "@/lib/api-error";
import { generatedOperation, isStockResource } from "@/lib/letron-api";
import { portalAuthBaseUrl } from "@/lib/portal-config";
import { APP_SESSION_COOKIES } from "@/lib/erp-auth-session";

const METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return proxy(request, context); }
export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return proxy(request, context); }
export async function PUT(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return proxy(request, context); }
export async function PATCH(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return proxy(request, context); }
export async function DELETE(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return proxy(request, context); }

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  if (!METHODS.has(request.method)) return apiErrorResponse("method_not_allowed", 405, "Method is not allowed.");
  const { path } = await context.params;
  if (!path?.length || !isStockResource(path[0])) return apiErrorResponse("unknown_stock_resource", 404, "Stock resource was not found.");
  const officialPath = `/api/v1/stock/${path.map((part) => encodeURIComponent(part)).join("/")}`;
  let operation;
  try { operation = generatedOperation(officialPath, request.method); } catch { return apiErrorResponse("unknown_stock_operation", 404, "Stock operation was not found."); }
  let body: ArrayBuffer | undefined;
  if (request.method !== "GET" && request.method !== "DELETE") {
    body = await request.arrayBuffer();
    if (request.headers.get("content-type")?.includes("application/json")) {
      try {
        const payload = JSON.parse(new TextDecoder().decode(body));
        generatedOperation(officialPath, request.method).request?.parse(payload);
      } catch (error) {
        return apiErrorResponse("stock_contract_invalid", 400, error instanceof Error ? error.message : "Stock payload is invalid.");
      }
    }
  }
  const headers = new Headers({ Accept: "application/json" });
  const session = (await cookies()).get(APP_SESSION_COOKIES.purchase)?.value;
  if (session) { headers.set("X-Letron-App-Session", session); headers.set("X-Letron-App", "purchase"); }
  const authorization = request.headers.get("authorization");
  if (authorization) headers.set("Authorization", authorization);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  let response: Response;
  try {
    response = await fetch(`${portalAuthBaseUrl()}/api/gateway${officialPath}${request.nextUrl.search}`, { method: request.method, headers, body, cache: "no-store" });
  } catch {
    return apiErrorResponse("gateway_unavailable", 503, "Letron Gateway is unavailable.", true);
  }
  if (!response.ok) return apiErrorFromResponse(response, "stock_request_failed");
  if (operation.response && response.headers.get("content-type")?.includes("application/json")) {
    try { operation.response.parse(await response.clone().json()); } catch { return apiErrorResponse("stock_response_invalid", 502, "Stock response did not match the generated contract.", true); }
  }
  return new NextResponse(response.body, { status: response.status, headers: { "content-type": response.headers.get("content-type") ?? "application/json" } });
}
