import type { NextApiRequest, NextApiResponse } from "next";

import { audit } from "../../../../src/server/audit";
import { pkceChallenge, randomToken } from "../../../../src/server/crypto";
import { appendSetCookie, disableCaching, firstQueryValue, redirectError, requestId, serializeCookie } from "../../../../src/server/http";
import { finishInteraction } from "../../../../src/server/interaction";
import { buildLarkAuthorizationUrl } from "../../../../src/server/lark";
import { LARK_TRANSACTION_COOKIE, LARK_TRANSACTION_TTL_SECONDS, saveOAuthTransaction } from "../../../../src/server/oauth-transaction";
import { getOidcProvider } from "../../../../src/server/oidc";
import { getUserBySessionToken, rotateSession, tokenFromRequest } from "../../../../src/server/session";
import { getEnv } from "../../../../src/server/env";
import { refreshLarkGroupsForUser } from "../../../../src/server/users";

function safeReturnTo(value: string | undefined): string {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/";
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
    res.redirect(303, buildLarkAuthorizationUrl({ state, codeChallenge: pkceChallenge(codeVerifier) }).toString());
  } catch {
    await audit({ eventType: "lark.login_start", outcome: "failure", requestId: requestId(req) }).catch(() => undefined);
    redirectError(res, "login_start_failed");
  }
}
