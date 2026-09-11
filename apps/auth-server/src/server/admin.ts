import type { NextApiRequest } from "next";

import { getEnv } from "./env";
import { GLOBAL_ACCESS_ADMIN_GROUP_ID } from "./runtime-config";
import { getUserBySessionToken, tokenFromRequest, type AuthenticatedUser } from "./session";

export async function adminUser(req: NextApiRequest): Promise<AuthenticatedUser | null> {
  const user = await getUserBySessionToken(tokenFromRequest(req));
  if (!user || !user.groupIds.includes(GLOBAL_ACCESS_ADMIN_GROUP_ID)) return null;
  return user;
}

export function isJsonRequest(req: NextApiRequest): boolean {
  return req.headers.accept?.includes("application/json") !== false;
}
