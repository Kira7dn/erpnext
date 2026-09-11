import { NextRequest, NextResponse } from "next/server";
import { portalAuthBaseUrl } from "@/lib/portal-config";

export function GET(request: NextRequest): NextResponse {
  const authBaseUrl = portalAuthBaseUrl();
  const requested = request.nextUrl.searchParams.get("return_to");
  const fallback = new URL("/accounts/bank-accounts", request.url);
  let returnTo = fallback;
  if (requested) {
    try {
      const candidate = new URL(requested, request.url);
      if (candidate.origin === request.nextUrl.origin && !candidate.pathname.startsWith("/api/")) returnTo = candidate;
    } catch { /* use the safe fallback */ }
  }
  const callback = new URL("/api/auth/oidc/callback", request.url);
  callback.searchParams.set("return_to", returnTo.pathname + returnTo.search);
  // Keep the browser on the public login entrypoint. The Lark callback remains
  // /api/auth/lark/callback, which is the URI registered in Lark Developer
  // Console; this route only selects the safe start URL.
  const loginUrl = new URL("/login/start", authBaseUrl);
  loginUrl.searchParams.set("handoff", "1");
  loginUrl.searchParams.set("return_to", callback.toString());
  return NextResponse.redirect(loginUrl, 303);
}
