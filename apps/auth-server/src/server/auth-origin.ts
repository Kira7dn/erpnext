import type { NextApiRequest } from "next";

import { getEnv } from "./env";

function headerValue(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value ?? "").split(",")[0].trim();
}

export function canonicalAuthOrigin(req: NextApiRequest): string {
  const envOrigin = new URL(getEnv().AUTH_BASE_URL);
  const host = headerValue(req.headers["x-forwarded-host"] || req.headers.host);
  const local = host === "localhost:3000" || host === "127.0.0.1:3000";
  if (!local && host !== envOrigin.host) return envOrigin.origin;
  const protocol = local ? "http" : envOrigin.protocol.replace(":", "");
  return `${protocol}://${host}`;
}
