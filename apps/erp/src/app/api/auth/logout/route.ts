import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export async function POST(): Promise<NextResponse> {
  const authBaseUrl = (process.env.LETRON_AUTH_BASE_URL ?? "http://localhost:3000").replace(/\/$/, "");
  const cookieHeader = (await cookies()).toString();
  const response = await fetch(`${authBaseUrl}/api/auth/logout`, {
    method: "POST",
    headers: cookieHeader ? { Cookie: cookieHeader } : undefined,
    redirect: "manual",
    cache: "no-store",
  });
  const nextResponse = NextResponse.redirect(new URL("/accounts/bank-accounts", process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3001"));
  const setCookie = response.headers.get("set-cookie");
  if (setCookie) nextResponse.headers.set("set-cookie", setCookie);
  return nextResponse;
}
