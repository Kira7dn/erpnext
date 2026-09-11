import "server-only";

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export const ERP_SESSION_COOKIE = "__Host-letron_erp_v2";
export const LEGACY_ERP_SESSION_COOKIE = "__Host-letron_erp";

export type ErpSession = { gatewaySession: string; token: string };

export async function getErpSession(
  rawToken?: string | null,
): Promise<ErpSession | null> {
  const token = rawToken ?? (await cookies()).get(ERP_SESSION_COOKIE)?.value;
  return token ? { gatewaySession: token, token } : null;
}

export function clearErpSessionCookies<T>(response: NextResponse<T>): NextResponse<T> {
  for (const name of [ERP_SESSION_COOKIE, LEGACY_ERP_SESSION_COOKIE]) {
    response.cookies.set(name, "", {
      expires: new Date(0),
      maxAge: 0,
      httpOnly: true,
      sameSite: "lax",
      secure: true,
      path: "/",
    });
  }
  return response;
}
