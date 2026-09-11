import { NextRequest, NextResponse } from "next/server";
import { portalAuthBaseUrl } from "@/lib/portal-config";

function isAppPath(pathname: string): boolean {
  return ["/assets", "/purchase", "/accounts"].some((root) => pathname === root || pathname.startsWith(`${root}/`));
}

export function GET(request: NextRequest): NextResponse {
  const authBaseUrl = portalAuthBaseUrl();
  const requested = request.nextUrl.searchParams.get("return_to");
  const fallback = new URL("/accounts", request.url);
  let returnTo = fallback;
  if (requested) {
    try {
      const candidate = new URL(requested, request.url);
      if (candidate.origin === request.nextUrl.origin && isAppPath(candidate.pathname)) returnTo = candidate;
    } catch { /* use the safe fallback */ }
  }
  const app = returnTo.pathname.startsWith("/assets") ? "assets" : returnTo.pathname.startsWith("/purchase") ? "purchase" : "accounts";
  const callback = new URL("/api/auth/session/callback", request.url);
  callback.searchParams.set("return_to", returnTo.pathname + returnTo.search);
  // Keep the browser on the public login entrypoint. The Lark callback remains
  // /api/auth/lark/callback, which is the URI registered in Lark Developer
  // Console; this route only selects the safe start URL.
  const loginUrl = new URL("/login/start", authBaseUrl);
  loginUrl.searchParams.set("app", app);
  loginUrl.searchParams.set("return_to", callback.toString());
  return NextResponse.redirect(loginUrl, 303);
}
