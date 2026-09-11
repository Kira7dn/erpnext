import { NextRequest, NextResponse } from "next/server";

import { portalAuthBaseUrl } from "@/lib/portal-config";
import { ERP_SESSION_COOKIE } from "@/lib/erp-auth-session";

function isAppPath(pathname: string): boolean {
  return ["/assets", "/purchase", "/accounts"].some(
    (root) => pathname === root || pathname.startsWith(`${root}/`),
  );
}

function safeReturnTo(request: NextRequest): string {
  const value = request.nextUrl.searchParams.get("return_to") ?? "/accounts";
  if (!value.startsWith("/") || value.startsWith("//") || !isAppPath(value))
    return "/accounts";
  return value;
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const handoff = request.nextUrl.searchParams.get("handoff") ?? "";
  if (!handoff)
    return NextResponse.json({ error: "handoff_missing" }, { status: 400 });
  const secret = process.env.LETRON_INTERNAL_API_SECRET?.trim();
  if (!secret)
    return NextResponse.json(
      { error: "erp_auth_not_configured" },
      { status: 503 },
    );
  let response: Response;
  try {
    response = await fetch(`${portalAuthBaseUrl()}/api/internal/erp/handoff`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${secret}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ code: handoff }),
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    return NextResponse.json({ error: "auth_unavailable" }, { status: 503 });
  }
  if (!response.ok)
    return NextResponse.json({ error: "handoff_invalid" }, { status: 401 });
  const payload = (await response.json()) as {
    user?: {
      id: string;
      email: string;
      displayName: string;
      avatarUrl: string | null;
    };
    gateway_session?: string;
    expires_at?: string;
  };
  if (!payload.user || !payload.gateway_session || !payload.expires_at)
    return NextResponse.json({ error: "handoff_invalid" }, { status: 401 });
  const next = NextResponse.redirect(
    new URL(safeReturnTo(request), request.url),
    303,
  );
  next.cookies.set(ERP_SESSION_COOKIE, payload.gateway_session, {
    expires: new Date(payload.expires_at),
    httpOnly: true,
    sameSite: "lax",
    secure: true,
    path: "/",
  });
  return next;
}
