import type { NextApiRequest, NextApiResponse } from "next";

import { audit } from "../../../../src/server/audit";
import { appendSetCookie, disableCaching, firstQueryValue, parseCookies, redirectError, requestId, serializeCookie } from "../../../../src/server/http";
import { finishInteraction } from "../../../../src/server/interaction";
import { exchangeLarkCode, fetchLarkGroupIds, fetchLarkIdentity } from "../../../../src/server/lark";
import { consumeOAuthTransaction, LARK_TRANSACTION_COOKIE } from "../../../../src/server/oauth-transaction";
import { getOidcProvider } from "../../../../src/server/oidc";
import { rotateSession } from "../../../../src/server/session";
import { upsertLarkUser } from "../../../../src/server/users";
import { getEnv } from "../../../../src/server/env";

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    res.status(405).end();
    return;
  }

  const id = requestId(req);
  const code = firstQueryValue(req.query.code);
  const state = firstQueryValue(req.query.state);
  const larkError = firstQueryValue(req.query.error);
  const browserBinding = parseCookies(req.headers.cookie)[LARK_TRANSACTION_COOKIE];
  if (larkError || !code || !state || !browserBinding) {
    await audit({ eventType: "lark.login", outcome: "failure", requestId: id, detail: { reason: "callback_rejected" } }).catch(() => undefined);
    redirectError(res, "lark_callback_rejected");
    return;
  }

  try {
    const transaction = await consumeOAuthTransaction(state, browserBinding);
    if (!transaction) throw new Error("OAUTH_TRANSACTION_INVALID");
    appendSetCookie(res, serializeCookie(LARK_TRANSACTION_COOKIE, "", {
      maxAge: 0,
      expires: new Date(0),
      secure: getEnv().AUTH_BASE_URL.startsWith("https://"),
    }));
    const accessToken = await exchangeLarkCode(code, transaction.codeVerifier, transaction.redirectUri);
    const identity = await fetchLarkIdentity(accessToken);
    const groupIds = getEnv().LARK_GROUP_SYNC_ENABLED
      ? await fetchLarkGroupIds(identity.subject, identity.subjectType)
      : undefined;
    const user = await upsertLarkUser({ ...identity, groupIds });
    if (user.status !== "ACTIVE") throw new Error("USER_DISABLED");
    await rotateSession(req, res, user.id);
    await audit({ eventType: "lark.login", outcome: "success", userId: user.id, requestId: id });

    if (transaction.interactionUid) {
      const interaction = await getOidcProvider().interactionDetails(req, res);
      if (interaction.uid !== transaction.interactionUid) throw new Error("OIDC_INTERACTION_MISMATCH");
      await finishInteraction(req, res, user.id);
      return;
    }
    res.redirect(303, transaction.returnTo ?? "/");
  } catch (error) {
    const reason = error instanceof Error && error.message.startsWith("LARK_") ? error.message : "login_failed";
    await audit({ eventType: "lark.login", outcome: "failure", requestId: id, detail: { reason } }).catch(() => undefined);
    if (!res.headersSent) redirectError(res, reason.toLowerCase());
  }
}
