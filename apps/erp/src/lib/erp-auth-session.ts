import "server-only";

import { cookies } from "next/headers";

export type AppKey = "assets" | "purchase" | "accounts";
export const APP_SESSION_COOKIES: Record<AppKey, string> = {
  assets: "__Host-letron_assets_session",
  purchase: "__Host-letron_purchase_session",
  accounts: "__Host-letron_accounts_session",
};
export const ERP_SESSION_COOKIE = APP_SESSION_COOKIES.accounts;
export const LEGACY_ERP_SESSION_COOKIE = "__Host-letron_erp_v2";

export type ErpSession = { gatewaySession: string; token: string };

export async function getErpSession(
  rawToken?: string | null,
  appKey: AppKey = "accounts",
): Promise<ErpSession | null> {
  const token = rawToken ?? (await cookies()).get(APP_SESSION_COOKIES[appKey])?.value;
  return token ? { gatewaySession: token, token } : null;
}
