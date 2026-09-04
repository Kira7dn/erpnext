import type { NextApiRequest, NextApiResponse } from "next";

import { getEnv } from "../../../src/server/env";
import { getOidcProvider } from "../../../src/server/oidc";

export const config = { api: { bodyParser: false, externalResolver: true } };

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  const originalUrl = req.url;
  const mountedRequest = req as NextApiRequest & { originalUrl?: string };
  const previousOriginalUrl = mountedRequest.originalUrl;
  const previousForwardedHost = req.headers["x-forwarded-host"];
  const previousForwardedProto = req.headers["x-forwarded-proto"];
  const canonical = new URL(getEnv().AUTH_BASE_URL);
  mountedRequest.originalUrl = originalUrl;
  req.headers["x-forwarded-host"] = canonical.host;
  req.headers["x-forwarded-proto"] = canonical.protocol.slice(0, -1);
  req.url = (req.url ?? "/").replace(/^\/api\/oidc/, "") || "/";
  try {
    await getOidcProvider().callback()(req, res);
  } finally {
    req.url = originalUrl;
    mountedRequest.originalUrl = previousOriginalUrl;
    req.headers["x-forwarded-host"] = previousForwardedHost;
    req.headers["x-forwarded-proto"] = previousForwardedProto;
  }
}
