import { NextRequest, NextResponse } from "next/server";
import { portalAuthBaseUrl } from "@/lib/portal-config";

export function GET(request: NextRequest): NextResponse {
  const authBaseUrl = portalAuthBaseUrl();
  const returnTo = new URL("/accounts/bank-accounts", request.url).toString();
  const loginUrl = new URL("/login", authBaseUrl);
  loginUrl.searchParams.set("return_to", returnTo);
  return NextResponse.redirect(loginUrl);
}
