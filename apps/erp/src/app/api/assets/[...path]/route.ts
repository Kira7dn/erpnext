import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromResponse, apiErrorResponse } from "@/lib/api-error";

import { isAssetResource, isAssetVirtualResource } from "@/lib/letron-api";
import { portalAuthBaseUrl } from "@/lib/portal-config";

const METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return proxy(request, context); }
export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return proxy(request, context); }
export async function PUT(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return proxy(request, context); }
export async function PATCH(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return proxy(request, context); }
export async function DELETE(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return proxy(request, context); }

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const startedAt = performance.now();
  if (!METHODS.has(request.method)) return apiErrorResponse("method_not_allowed", 405, "Method is not allowed.");
  const { path } = await context.params;
  if (!path?.length || (!isAssetResource(path[0]) && !isAssetVirtualResource(path[0]))) return apiErrorResponse("unknown_asset_resource", 404, "Asset resource was not found.");
  const target = `${portalAuthBaseUrl()}/api/gateway/api/v1/assets/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const headers = new Headers({ Accept: "application/json" });
  const cookieHeader = (await cookies()).toString();
  if (cookieHeader) headers.set("Cookie", cookieHeader);
  const authorization = request.headers.get("authorization");
  if (authorization) headers.set("Authorization", authorization);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  let response: Response;
  try {
    response = await fetch(target, { method: request.method, headers, body: request.method === "GET" || request.method === "DELETE" ? undefined : await request.arrayBuffer(), cache: "no-store" });
  } catch {
    return apiErrorResponse("gateway_unavailable", 503, "Letron Global Portal Gateway is unavailable.", true);
  }
  if (!response.ok)
    return apiErrorFromResponse(response, "asset_request_failed");
  const responseHeaders = new Headers({ "content-type": response.headers.get("content-type") ?? "application/json" });
  const gatewayTiming = response.headers.get("server-timing");
  if (gatewayTiming) responseHeaders.set("Server-Timing", `${gatewayTiming}, erp_route;dur=${(performance.now() - startedAt).toFixed(1)}`);
  return new NextResponse(response.body, { status: response.status, headers: responseHeaders });
}
