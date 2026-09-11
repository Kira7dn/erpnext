import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
const SESSION_COOKIES = [["/assets", "__Host-letron_assets_session"], ["/purchase", "__Host-letron_purchase_session"], ["/accounts", "__Host-letron_accounts_session"]] as const;

export function proxy(request: NextRequest) {
  if (
    request.nextUrl.pathname.endsWith("/manifest.webmanifest") ||
    request.nextUrl.pathname.endsWith("/icon.svg")
  )
    return NextResponse.next();
  if (
    request.nextUrl.pathname === "/supplier" ||
    request.nextUrl.pathname.startsWith("/supplier/")
  )
    return NextResponse.next();
  const sessionCookie = SESSION_COOKIES.find(([root]) => request.nextUrl.pathname === root || request.nextUrl.pathname.startsWith(`${root}/`))?.[1];
  if (sessionCookie && request.cookies.has(sessionCookie)) return NextResponse.next();

  const loginUrl = new URL("/api/auth/login", request.url);
  loginUrl.searchParams.set(
    "return_to",
    `${request.nextUrl.pathname}${request.nextUrl.search}`,
  );
  return NextResponse.redirect(loginUrl, 303);
}

export const config = {
  // Protect every ERP page automatically. API routes and static assets have
  // their own guards or must remain publicly fetchable by the framework.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
