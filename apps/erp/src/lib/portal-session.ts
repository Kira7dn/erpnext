import { cache } from "react";
import { getErpSession } from "./erp-auth-session";

export type PortalUser = {
  email: string;
  displayName: string;
  avatarUrl: string | null;
};

export const getPortalUser = cache(async (): Promise<PortalUser | null> => {
  const session = await getErpSession();
  return session?.user ? {
    email: session.user.email,
    displayName: session.user.displayName,
    avatarUrl: session.user.avatarUrl,
  } : null;
});
