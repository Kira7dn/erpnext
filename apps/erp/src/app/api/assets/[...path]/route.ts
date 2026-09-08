import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

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
  if (!METHODS.has(request.method)) return NextResponse.json({ error: "method_not_allowed" }, { status: 405 });
  const { path } = await context.params;
  if (!path?.length || (!isAssetResource(path[0]) && !isAssetVirtualResource(path[0]))) return NextResponse.json({ error: "unknown_asset_resource" }, { status: 404 });
  const target = `${portalAuthBaseUrl()}/api/gateway/api/v1/assets/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const headers = new Headers({ Accept: "application/json" });
  const cookieHeader = (await cookies()).toString();
  if (cookieHeader) headers.set("Cookie", cookieHeader);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const response = await fetch(target, { method: request.method, headers, body: request.method === "GET" || request.method === "DELETE" ? undefined : await request.arrayBuffer(), cache: "no-store" });
  const responseHeaders = new Headers({ "content-type": response.headers.get("content-type") ?? "application/json" });
  const gatewayTiming = response.headers.get("server-timing");
  if (gatewayTiming) responseHeaders.set("Server-Timing", `${gatewayTiming}, erp_route;dur=${(performance.now() - startedAt).toFixed(1)}`);
  return new NextResponse(response.body, { status: response.status, headers: responseHeaders });
}
