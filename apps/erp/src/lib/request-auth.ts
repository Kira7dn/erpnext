import "server-only";

import { cookies } from "next/headers";

export async function requestAuthCredential(request: Request): Promise<string> {
  const cookieHeader = (await cookies()).toString();
  if (cookieHeader) return cookieHeader;

  const authorization = request.headers.get("authorization")?.trim() ?? "";
  return /^Bearer\s+\S+$/i.test(authorization) ? authorization : "";
}
