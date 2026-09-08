import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { portalAppBaseUrl, portalAuthBaseUrl } from "@/lib/portal-config";

const SESSION_COOKIE = "letron_sso";

function authLoginUrl(request: NextRequest): URL {
  const authBaseUrl = portalAuthBaseUrl();
  const appBaseUrl = portalAppBaseUrl(request.nextUrl.origin);
  const returnTo = new URL(`${request.nextUrl.pathname}${request.nextUrl.search}`, appBaseUrl);
  const loginUrl = new URL("/login", authBaseUrl);
  loginUrl.searchParams.set("return_to", returnTo.toString());
  return loginUrl;
}

export function proxy(request: NextRequest) {
  if (request.nextUrl.pathname.endsWith("/manifest.webmanifest") || request.nextUrl.pathname.endsWith("/icon.svg")) return NextResponse.next();
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();

  return NextResponse.redirect(authLoginUrl(request));
}

export const config = {
  // Protect every ERP page automatically. API routes and static assets have
  // their own guards or must remain publicly fetchable by the framework.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
