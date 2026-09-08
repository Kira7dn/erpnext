import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { isPurchaseResource } from "@/lib/letron-api";
import { portalAuthBaseUrl } from "@/lib/portal-config";

const METHODS = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);
const OFFICIAL_MODULES: Record<string, string> = {
  suppliers: "buying/suppliers",
  contacts: "contacts/contacts",
  addresses: "contacts/addresses",
  items: "stock/items",
  "material-requests": "stock/material-requests",
  "request-for-quotations": "crm/request-for-quotations",
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
    return NextResponse.json({ error: "method_not_allowed" }, { status: 405 });
  const { path } = await context.params;
  if (!path?.length || !isPurchaseResource(path[0]))
    return NextResponse.json(
      { error: "unknown_purchase_resource" },
      { status: 404 },
    );
  const officialPath = `${OFFICIAL_MODULES[path[0]]}${path
    .slice(1)
    .map((part) => `/${encodeURIComponent(part)}`)
    .join("")}`;
  const target = `${portalAuthBaseUrl()}/api/gateway/api/v1/${officialPath}${request.nextUrl.search}`;
  const headers = new Headers({ Accept: "application/json" });
  const cookieHeader = (await cookies()).toString();
  if (cookieHeader) headers.set("Cookie", cookieHeader);
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
    return NextResponse.json({ error: "gateway_unavailable" }, { status: 503 });
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
