import { cache } from "react";
import { cookies } from "next/headers";
import { ERP_SESSION_COOKIE } from "./erp-auth-session";

export type PortalUser = {
  email: string;
  displayName: string;
  avatarUrl: string | null;
};

export const getPortalUser = cache(async (): Promise<PortalUser | null> => {
  const token = (await cookies()).get(ERP_SESSION_COOKIE)?.value;
  return token
    ? { email: "", displayName: "Đã đăng nhập", avatarUrl: null }
    : null;
});
