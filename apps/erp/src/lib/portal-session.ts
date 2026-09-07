import { cookies } from "next/headers";

export type PortalUser = {
  email: string;
  displayName: string;
  avatarUrl: string | null;
};

export async function getPortalUser(): Promise<PortalUser | null> {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader) return null;
  const authBaseUrl = (process.env.LETRON_AUTH_BASE_URL ?? "http://localhost:3000").replace(/\/$/, "");
  const response = await fetch(`${authBaseUrl}/api/auth/session`, {
    headers: { Cookie: cookieHeader },
    cache: "no-store",
  });
  if (!response.ok) return null;
  const payload = await response.json() as { user?: PortalUser };
  return payload.user ?? null;
}
