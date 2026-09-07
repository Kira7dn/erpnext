import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { isAssetResource, isAssetVirtualResource } from "@/lib/letron-api";

const METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return proxy(request, context); }
export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return proxy(request, context); }
export async function PUT(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return proxy(request, context); }
export async function PATCH(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return proxy(request, context); }
export async function DELETE(request: NextRequest, context: { params: Promise<{ path: string[] }> }) { return proxy(request, context); }

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  if (!METHODS.has(request.method)) return NextResponse.json({ error: "method_not_allowed" }, { status: 405 });
  const { path } = await context.params;
  if (!path?.length || (!isAssetResource(path[0]) && !isAssetVirtualResource(path[0]))) return NextResponse.json({ error: "unknown_asset_resource" }, { status: 404 });
  const target = `${process.env.LETRON_AUTH_BASE_URL ?? "http://localhost:3000"}/api/gateway/api/v1/assets/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const headers = new Headers({ Accept: "application/json" });
  const cookieHeader = (await cookies()).toString();
  if (cookieHeader) headers.set("Cookie", cookieHeader);
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const response = await fetch(target, { method: request.method, headers, body: request.method === "GET" || request.method === "DELETE" ? undefined : await request.arrayBuffer(), cache: "no-store" });
  return new NextResponse(response.body, { status: response.status, headers: { "content-type": response.headers.get("content-type") ?? "application/json" } });
}
