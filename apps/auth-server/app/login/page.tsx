import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { getUserBySessionToken, SESSION_COOKIE } from "../../src/server/session";
import { getEnv } from "../../src/server/env";

export const dynamic = "force-dynamic";

function safeReturnTo(value: string | undefined): string {
  if (!value) return "/";
  if (value.startsWith("/") && !value.startsWith("//")) return value;
  const configured = getEnv().LETRON_ERP_APP_BASE_URL;
  try {
    const requested = new URL(value);
    return requested.origin === new URL(configured).origin ? requested.toString() : "/";
  } catch {
    return "/";
  }
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ uid?: string; return_to?: string }>;
}) {
  const [{ uid, return_to: returnTo }, cookieStore] = await Promise.all([searchParams, cookies()]);
  const user = await getUserBySessionToken(cookieStore.get(SESSION_COOKIE)?.value);
  if (user && uid) redirect("/api/auth/session/continue");
  if (user) {
    const refreshUrl = new URL("/api/auth/session/refresh", "http://auth.local");
    refreshUrl.searchParams.set("return_to", safeReturnTo(returnTo));
    redirect(`${refreshUrl.pathname}${refreshUrl.search}`);
  }
  const query = new URLSearchParams();
  if (uid) query.set("uid", uid);
  if (returnTo) query.set("return_to", returnTo);
  redirect(`/api/auth/start${query.toString() ? `?${query.toString()}` : ""}`);
}
