import { NextRequest, NextResponse } from "next/server";

export function GET(request: NextRequest): NextResponse {
  const authBaseUrl = (process.env.LETRON_AUTH_BASE_URL ?? "http://localhost:3000").replace(/\/$/, "");
  const returnTo = new URL("/accounts/bank-accounts", request.url).toString();
  const loginUrl = new URL("/login", authBaseUrl);
  loginUrl.searchParams.set("return_to", returnTo);
  return NextResponse.redirect(loginUrl);
}
