import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { getEnv } from "../../../src/server/env";
import { GLOBAL_ACCESS_ADMIN_GROUP_ID } from "../../../src/server/runtime-config";
import { getUserBySessionToken, SESSION_COOKIE } from "../../../src/server/session";
import AccessPolicyAdmin from "./policy-admin";

export const dynamic = "force-dynamic";

export default async function AccessPolicyPage() {
  const user = await getUserBySessionToken((await cookies()).get(SESSION_COOKIE)?.value);
  getEnv();
  if (!user || !user.groupIds.includes(GLOBAL_ACCESS_ADMIN_GROUP_ID)) redirect("/");
  return <AccessPolicyAdmin />;
}
