import { NextRequest, NextResponse } from "next/server";
import {
  APP_SESSION_COOKIES,
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
  const returnTo = safeReturnTo(request);
  const app = returnTo.startsWith("/assets") ? "assets" : returnTo.startsWith("/purchase") ? "purchase" : "accounts";
  const session = await getErpSession(undefined, app);
  if (session?.gatewaySession && process.env.LETRON_INTERNAL_API_SECRET)
    await fetch(`${authBaseUrl}/api/internal/app/logout`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${process.env.LETRON_INTERNAL_API_SECRET}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ session: session.gatewaySession, app }),
      cache: "no-store",
    }).catch(() => undefined);
  const nextResponse = NextResponse.redirect(
    new URL(
      returnTo,
      portalAppBaseUrl(new URL(request.url).origin),
    ),
  );
  nextResponse.cookies.set(APP_SESSION_COOKIES[app], "", {
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
