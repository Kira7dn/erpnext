import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { getUserBySessionToken, SESSION_COOKIE } from "../../src/server/session";

export const dynamic = "force-dynamic";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ uid?: string }>;
}) {
  const [{ uid }, cookieStore] = await Promise.all([searchParams, cookies()]);
  const user = await getUserBySessionToken(cookieStore.get(SESSION_COOKIE)?.value);
  if (user && uid) redirect("/api/auth/session/continue");
  if (user) redirect("/");
  redirect(`/api/auth/lark/start${uid ? `?uid=${encodeURIComponent(uid)}` : ""}`);
}
