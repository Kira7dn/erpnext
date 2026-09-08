import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { portalAppBaseUrl, portalAuthBaseUrl } from "@/lib/portal-config";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const authBaseUrl = portalAuthBaseUrl();
  const cookieHeader = (await cookies()).toString();
  const response = await fetch(`${authBaseUrl}/api/auth/logout`, {
    method: "POST",
    headers: cookieHeader ? { Cookie: cookieHeader } : undefined,
    redirect: "manual",
    cache: "no-store",
  });
  const nextResponse = NextResponse.redirect(new URL("/accounts/bank-accounts", portalAppBaseUrl(new URL(request.url).origin)));
  const setCookie = response.headers.get("set-cookie");
  if (setCookie) nextResponse.headers.set("set-cookie", setCookie);
  return nextResponse;
}
