import type { NextApiRequest, NextApiResponse } from "next";

import { audit } from "../../../../src/server/audit";
import { pkceChallenge, randomToken } from "../../../../src/server/crypto";
import { appendSetCookie, disableCaching, firstQueryValue, redirectError, requestId, serializeCookie } from "../../../../src/server/http";
import { finishInteraction } from "../../../../src/server/interaction";
import { buildLarkAuthorizationUrl, larkCallbackUri } from "../../../../src/server/lark";
import { LARK_TRANSACTION_COOKIE, LARK_TRANSACTION_TTL_SECONDS, saveOAuthTransaction } from "../../../../src/server/oauth-transaction";
import { getOidcProvider } from "../../../../src/server/oidc";
import { getUserBySessionToken, rotateSession, tokenFromRequest } from "../../../../src/server/session";
import { getEnv } from "../../../../src/server/env";
import { refreshLarkGroupsForUser } from "../../../../src/server/users";

function safeReturnTo(value: string | undefined): string {
  if (!value) return "/";
  if (value.startsWith("/") && !value.startsWith("//")) return value;
  const configured = getEnv().LETRON_NEXT_BASE_URL;
  if (!configured) return "/";
  try {
    const requested = new URL(value);
    const allowed = new URL(configured);
    return requested.origin === allowed.origin ? requested.toString() : "/";
  } catch {
    return "/";
  }
}

function requestOrigin(req: NextApiRequest): string {
  const forwardedHost = Array.isArray(req.headers["x-forwarded-host"]) ? req.headers["x-forwarded-host"][0] : req.headers["x-forwarded-host"];
  const host = (forwardedHost ?? req.headers.host ?? "").split(",")[0].trim();
  const allowedHosts = new Set(["localhost:3000", "127.0.0.1:3000", "auth.letron.vn", "erp-one-henna.vercel.app"]);
  if (!allowedHosts.has(host)) return getEnv().AUTH_BASE_URL;
  const forwardedProto = Array.isArray(req.headers["x-forwarded-proto"]) ? req.headers["x-forwarded-proto"][0] : req.headers["x-forwarded-proto"];
  const protocol = forwardedProto?.split(",")[0].trim() || (host.startsWith("localhost:") || host.startsWith("127.0.0.1:") ? "http" : "https");
  return `${protocol}://${host}`;
}

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    res.status(405).end();
    return;
  }

  const uid = firstQueryValue(req.query.uid);
  try {
    const redirectUri = larkCallbackUri(requestOrigin(req));
    if (uid) {
      const interaction = await getOidcProvider().interactionDetails(req, res);
      if (interaction.uid !== uid) throw new Error("OIDC_INTERACTION_MISMATCH");
      const existingUser = await getUserBySessionToken(tokenFromRequest(req));
      if (existingUser) {
        try {
          if (getEnv().LARK_GROUP_SYNC_ENABLED) await refreshLarkGroupsForUser(existingUser.id);
          await rotateSession(req, res, existingUser.id);
          await finishInteraction(req, res, existingUser.id);
          return;
        } catch (error) {
          if (!(error instanceof Error) || error.message !== "LARK_IDENTITY_REAUTH_REQUIRED") throw error;
        }
      }
    }

    const state = randomToken();
    const browserBinding = randomToken();
    const codeVerifier = randomToken(48);
    await saveOAuthTransaction({
      state,
      browserBinding,
      codeVerifier,
      interactionUid: uid,
      returnTo: uid ? undefined : safeReturnTo(firstQueryValue(req.query.return_to)),
    });
    appendSetCookie(res, serializeCookie(LARK_TRANSACTION_COOKIE, browserBinding, {
      maxAge: LARK_TRANSACTION_TTL_SECONDS,
      secure: getEnv().AUTH_BASE_URL.startsWith("https://"),
    }));
    res.redirect(303, buildLarkAuthorizationUrl({ state, codeChallenge: pkceChallenge(codeVerifier), redirectUri }).toString());
  } catch {
    await audit({ eventType: "lark.login_start", outcome: "failure", requestId: requestId(req) }).catch(() => undefined);
    redirectError(res, "login_start_failed");
  }
}
