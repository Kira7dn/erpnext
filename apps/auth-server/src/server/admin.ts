import type { NextApiRequest } from "next";

import { getEnv } from "./env";
import { getUserBySessionToken, tokenFromRequest, type AuthenticatedUser } from "./session";

export async function adminUser(req: NextApiRequest): Promise<AuthenticatedUser | null> {
  const user = await getUserBySessionToken(tokenFromRequest(req));
  const groupId = getEnv().GLOBAL_ACCESS_ADMIN_GROUP_ID;
  if (!user || !groupId || !user.groupIds.includes(groupId)) return null;
  return user;
}

export function isJsonRequest(req: NextApiRequest): boolean {
  return req.headers.accept?.includes("application/json") !== false;
}
