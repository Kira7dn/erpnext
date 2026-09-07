import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const SESSION_COOKIE = "letron_sso";

function authLoginUrl(request: NextRequest): URL {
  const authBaseUrl = (process.env.LETRON_AUTH_BASE_URL ?? "http://localhost:3000").replace(/\/$/, "");
  const appBaseUrl = (process.env.NEXT_PUBLIC_APP_URL ?? request.nextUrl.origin).replace(/\/$/, "");
  const returnTo = new URL(`${request.nextUrl.pathname}${request.nextUrl.search}`, appBaseUrl);
  const loginUrl = new URL("/login", authBaseUrl);
  loginUrl.searchParams.set("return_to", returnTo.toString());
  return loginUrl;
}

export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();

  return NextResponse.redirect(authLoginUrl(request));
}

export const config = {
  matcher: ["/accounts/:path*", "/assets/:path*"],
};
