import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
const ERP_SESSION_COOKIE = "__Host-letron_erp_v2";

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
  if (request.cookies.has(ERP_SESSION_COOKIE)) return NextResponse.next();

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
