import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { isAccountingResource } from "@/lib/letron-api";
import { portalAuthBaseUrl } from "@/lib/portal-config";

const ALLOWED_METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}

export async function PUT(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}

export async function PATCH(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  if (!ALLOWED_METHODS.has(request.method)) return NextResponse.json({ error: "method_not_allowed" }, { status: 405 });
  const { path } = await context.params;
  if (!path?.length || !isAccountingResource(path[0])) return NextResponse.json({ error: "unknown_accounting_resource" }, { status: 404 });

  const target = `${portalAuthBaseUrl()}/api/gateway/api/v1/accounts/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const forwardedHeaders = new Headers({ Accept: "application/json" });
  const cookieHeader = (await cookies()).toString();
  if (cookieHeader) forwardedHeaders.set("Cookie", cookieHeader);
  const contentType = request.headers.get("content-type");
  if (contentType) forwardedHeaders.set("Content-Type", contentType);

  const response = await fetch(target, {
    method: request.method,
    headers: forwardedHeaders,
    body: request.method === "GET" || request.method === "DELETE" ? undefined : await request.arrayBuffer(),
    cache: "no-store",
  });
  return new NextResponse(response.body, { status: response.status, headers: { "content-type": response.headers.get("content-type") ?? "application/json" } });
}
