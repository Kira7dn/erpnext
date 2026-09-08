import { cookies } from "next/headers";
import { cache } from "react";
import { portalAuthBaseUrl } from "./portal-config";

export type PortalUser = {
  email: string;
  displayName: string;
  avatarUrl: string | null;
};

export const getPortalUser = cache(async (): Promise<PortalUser | null> => {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader) return null;
  const authBaseUrl = portalAuthBaseUrl();
  const response = await fetch(`${authBaseUrl}/api/auth/session`, {
    headers: { Cookie: cookieHeader },
    cache: "no-store",
  });
  if (!response.ok) return null;
  const payload = await response.json() as { user?: PortalUser };
  return payload.user ?? null;
});
