import "server-only";

import { cookies } from "next/headers";

export const ERP_SESSION_COOKIE = "__Host-letron_erp";

export type ErpSession = { gatewaySession: string; token: string };

export async function getErpSession(
  rawToken?: string | null,
): Promise<ErpSession | null> {
  const token = rawToken ?? (await cookies()).get(ERP_SESSION_COOKIE)?.value;
  return token ? { gatewaySession: token, token } : null;
}
