import { NextRequest, NextResponse } from "next/server";
import { ERP_SESSION_COOKIE, getErpSession, revokeErpSession } from "@/lib/erp-auth-session";
import { portalAppBaseUrl, portalAuthBaseUrl } from "@/lib/portal-config";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const authBaseUrl = portalAuthBaseUrl();
  const session = await getErpSession();
  if (session?.gatewaySession && process.env.LETRON_INTERNAL_API_SECRET) await fetch(`${authBaseUrl}/api/internal/erp/logout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${process.env.LETRON_INTERNAL_API_SECRET}`, "Content-Type": "application/json" },
    body: JSON.stringify({ gateway_session: session.gatewaySession }),
    cache: "no-store",
  }).catch(() => undefined);
  await revokeErpSession(session?.token);
  const nextResponse = NextResponse.redirect(new URL("/accounts/bank-accounts", portalAppBaseUrl(new URL(request.url).origin)));
  nextResponse.cookies.set(ERP_SESSION_COOKIE, "", { expires: new Date(0), maxAge: 0, httpOnly: true, sameSite: "lax", secure: true, path: "/" });
  return nextResponse;
}
