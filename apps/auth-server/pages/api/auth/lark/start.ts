import type { NextApiRequest, NextApiResponse } from "next";

import { audit } from "../../../../src/server/audit";
import { pkceChallenge, randomToken } from "../../../../src/server/crypto";
import { appendSetCookie, disableCaching, firstQueryValue, redirectError, requestId, requestIsSecure, serializeCookie } from "../../../../src/server/http";
import { finishInteraction } from "../../../../src/server/interaction";
import { buildLarkAuthorizationUrl, larkCallbackUri } from "../../../../src/server/lark";
import { LARK_TRANSACTION_COOKIE, LARK_TRANSACTION_TTL_SECONDS, saveOAuthTransaction } from "../../../../src/server/oauth-transaction";
import { getOidcProvider } from "../../../../src/server/oidc";
import { getUserBySessionToken, rotateSession, tokenFromRequest } from "../../../../src/server/session";
import { getEnv } from "../../../../src/server/env";
import { canonicalAuthOrigin } from "../../../../src/server/auth-origin";

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

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    res.status(405).end();
    return;
  }

  const uid = firstQueryValue(req.query.uid);
  try {
    const redirectUri = larkCallbackUri(canonicalAuthOrigin(req));
    if (uid) {
      const interaction = await getOidcProvider().interactionDetails(req, res);
      if (interaction.uid !== uid) throw new Error("OIDC_INTERACTION_MISMATCH");
      const existingUser = await getUserBySessionToken(tokenFromRequest(req));
      if (existingUser) {
        try {
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
      secure: requestIsSecure(req),
    }));
    res.redirect(303, buildLarkAuthorizationUrl({ state, codeChallenge: pkceChallenge(codeVerifier), redirectUri }).toString());
  } catch {
    await audit({ eventType: "lark.login_start", outcome: "failure", requestId: requestId(req) }).catch(() => undefined);
    redirectError(res, "login_start_failed");
  }
}
