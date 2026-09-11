import { NextRequest, NextResponse } from "next/server";
import { portalAuthBaseUrl } from "@/lib/portal-config";
import { APP_SESSION_COOKIES, type AppKey } from "@/lib/erp-auth-session";

function isAppPath(pathname: string): boolean { return ["/assets", "/purchase", "/accounts"].some((root) => pathname === root || pathname.startsWith(`${root}/`)); }
function safeReturnTo(request: NextRequest): string { const value = request.nextUrl.searchParams.get("return_to") ?? "/accounts"; return value.startsWith("/") && !value.startsWith("//") && isAppPath(value) ? value : "/accounts"; }
export async function GET(request: NextRequest): Promise<NextResponse> {
  const grant = request.nextUrl.searchParams.get("grant") ?? "";
  if (!grant) return NextResponse.json({ error: "grant_missing" }, { status: 400 });
  const secret = process.env.LETRON_INTERNAL_API_SECRET?.trim();
  if (!secret) return NextResponse.json({ error: "erp_auth_not_configured" }, { status: 503 });
  const returnTo = safeReturnTo(request);
  const app: AppKey = returnTo.startsWith("/assets") ? "assets" : returnTo.startsWith("/purchase") ? "purchase" : "accounts";
  let response: Response;
  try { response = await fetch(`${portalAuthBaseUrl()}/api/internal/app/session`, { method: "POST", headers: { Authorization: `Bearer ${secret}`, "Content-Type": "application/json" }, body: JSON.stringify({ code: grant, app }), cache: "no-store", signal: AbortSignal.timeout(15_000) }); }
  catch { return NextResponse.json({ error: "auth_unavailable" }, { status: 503 }); }
  if (!response.ok) return NextResponse.json({ error: "grant_invalid" }, { status: 401 });
  const payload = await response.json() as { session?: string; expires_at?: string };
  if (!payload.session || !payload.expires_at) return NextResponse.json({ error: "grant_invalid" }, { status: 401 });
  const next = NextResponse.redirect(new URL(returnTo, request.url), 303);
  next.cookies.set(APP_SESSION_COOKIES[app], payload.session, { expires: new Date(payload.expires_at), httpOnly: true, sameSite: "lax", secure: true, path: "/" });
  return next;
}
