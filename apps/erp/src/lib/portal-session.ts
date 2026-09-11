import { cache } from "react";
import { cookies } from "next/headers";
import { APP_SESSION_COOKIES, type AppKey } from "./erp-auth-session";
import { portalAuthBaseUrl } from "./portal-config";

export type PortalUser = {
  email: string;
  displayName: string;
  avatarUrl: string | null;
};

export const getPortalUser = cache(async (appKey: AppKey): Promise<PortalUser | null> => {
  const token = (await cookies()).get(APP_SESSION_COOKIES[appKey])?.value;
  const secret = process.env.LETRON_INTERNAL_API_SECRET?.trim();
  if (!token || !secret) return null;
  try {
    const response = await fetch(`${portalAuthBaseUrl()}/api/internal/app/introspect`, {
      method: "POST",
      headers: { Authorization: `Bearer ${secret}`, "Content-Type": "application/json" },
      body: JSON.stringify({ session: token, app: appKey }),
      cache: "no-store",
    });
    if (!response.ok) return null;
    const payload = await response.json() as { user?: PortalUser };
    return payload.user?.displayName ? payload.user : null;
  } catch { return null; }
});
