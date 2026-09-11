import { NextRequest, NextResponse } from "next/server";
import {
  ERP_SESSION_COOKIE,
  getErpSession,
  LEGACY_ERP_SESSION_COOKIE,
} from "@/lib/erp-auth-session";
import { portalAppBaseUrl, portalAuthBaseUrl } from "@/lib/portal-config";

function safeReturnTo(request: NextRequest): string {
  const requested =
    request.nextUrl.searchParams.get("return_to") ?? "/accounts";
  if (
    !requested.startsWith("/") ||
    requested.startsWith("//") ||
    requested.startsWith("/api/")
  )
    return "/accounts";
  const root = ["/assets", "/purchase", "/accounts"].find(
    (value) => requested === value || requested.startsWith(`${value}/`),
  );
  return root ? requested : "/accounts";
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const authBaseUrl = portalAuthBaseUrl();
  const session = await getErpSession();
  if (session?.gatewaySession && process.env.LETRON_INTERNAL_API_SECRET)
    await fetch(`${authBaseUrl}/api/internal/erp/logout`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${process.env.LETRON_INTERNAL_API_SECRET}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ gateway_session: session.gatewaySession }),
      cache: "no-store",
    }).catch(() => undefined);
  const nextResponse = NextResponse.redirect(
    new URL(
      safeReturnTo(request),
      portalAppBaseUrl(new URL(request.url).origin),
    ),
  );
  nextResponse.cookies.set(ERP_SESSION_COOKIE, "", {
    expires: new Date(0),
    maxAge: 0,
    httpOnly: true,
    sameSite: "lax",
    secure: true,
    path: "/",
  });
  nextResponse.cookies.set(LEGACY_ERP_SESSION_COOKIE, "", {
    expires: new Date(0),
    maxAge: 0,
    httpOnly: true,
    sameSite: "lax",
    secure: true,
    path: "/",
  });
  return nextResponse;
}
