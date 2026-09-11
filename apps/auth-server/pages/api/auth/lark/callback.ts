import type { NextApiRequest, NextApiResponse } from "next";

import { audit } from "../../../../src/server/audit";
import { sha256 } from "../../../../src/server/crypto";
import { getDb } from "../../../../src/server/db";
import {
  appendSetCookie,
  disableCaching,
  firstQueryValue,
  parseCookies,
  redirectError,
  requestId,
  requestIsSecure,
  serializeCookie,
} from "../../../../src/server/http";
import { finishInteraction } from "../../../../src/server/interaction";
import {
  exchangeLarkCode,
  fetchLarkGroupIds,
  fetchLarkIdentity,
  larkCallbackUri,
} from "../../../../src/server/lark";
import {
  consumeOAuthTransaction,
  LARK_TRANSACTION_COOKIE,
} from "../../../../src/server/oauth-transaction";
import { getOidcProvider } from "../../../../src/server/oidc";
import { AUTH_FEATURE_CONFIG } from "../../../../src/server/env";
import { rotateSession } from "../../../../src/server/session";
import { upsertLarkUser } from "../../../../src/server/users";
import { canonicalAuthOrigin } from "../../../../src/server/auth-origin";
import {
  completeLarkMailOAuth,
  LARK_MAIL_OAUTH_COOKIE,
} from "../../../../src/server/lark-mail";
import { createErpHandoff, type AppKey } from "../../../../src/server/erp-handoff";

export default async function handler(
  req: NextApiRequest,
  res: NextApiResponse,
): Promise<void> {
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
  const mailBinding = parseCookies(req.headers.cookie)[LARK_MAIL_OAUTH_COOKIE];
  const mailTransaction = state
    ? await getDb().larkMailOAuthTransaction.findUnique({
        where: { stateHash: sha256(state) },
        select: { id: true },
      })
    : null;
  if (!larkError && code && state && mailBinding && mailTransaction) {
    try {
      const expectedMailbox = await completeLarkMailOAuth({
        state,
        binding: mailBinding,
        code,
      });
      appendSetCookie(
        res,
        serializeCookie(LARK_MAIL_OAUTH_COOKIE, "", {
          maxAge: 0,
          expires: new Date(0),
          secure: requestIsSecure(req),
        }),
      );
      await audit({
        eventType: "lark.mail_oauth",
        outcome: "success",
        detail: { mailbox: expectedMailbox },
      });
      res
        .status(200)
        .json({
          ok: true,
          mailbox: expectedMailbox,
          message: "Lark Mail authorization stored",
        });
    } catch (error) {
      await audit({
        eventType: "lark.mail_oauth",
        outcome: "failure",
        detail: {
          reason:
            error instanceof Error ? error.message.slice(0, 80) : "unknown",
        },
      }).catch(() => undefined);
      res.status(400).json({ error: "mail_oauth_failed" });
    }
    return;
  }
  const browserBinding = parseCookies(req.headers.cookie)[
    LARK_TRANSACTION_COOKIE
  ];
  if (larkError || !code || !state || !browserBinding) {
    await audit({
      eventType: "lark.login",
      outcome: "failure",
      requestId: id,
      detail: { reason: "callback_rejected" },
    }).catch(() => undefined);
    redirectError(res, "lark_callback_rejected");
    return;
  }

  try {
    const transaction = await consumeOAuthTransaction(state, browserBinding);
    if (!transaction) throw new Error("OAUTH_TRANSACTION_INVALID");
    appendSetCookie(
      res,
      serializeCookie(LARK_TRANSACTION_COOKIE, "", {
        maxAge: 0,
        expires: new Date(0),
        secure: requestIsSecure(req),
      }),
    );
    const accessToken = await exchangeLarkCode(
      code,
      transaction.codeVerifier,
      larkCallbackUri(canonicalAuthOrigin(req)),
    );
    const identity = await fetchLarkIdentity(accessToken);
    const groupIds = AUTH_FEATURE_CONFIG.larkGroupSyncEnabled
      ? await fetchLarkGroupIds(identity.subject, identity.subjectType)
      : undefined;
    const user = await upsertLarkUser({ ...identity, groupIds });
    if (user.status !== "ACTIVE") throw new Error("USER_DISABLED");
    if (transaction.appKey && transaction.returnTo) {
      const handoff = await createErpHandoff(user.id, (transaction.appKey as AppKey | null) ?? "accounts");
      await audit({
        eventType: "lark.login",
        outcome: "success",
        userId: user.id,
        requestId: id,
        detail: { flow: "app_session_grant", app: transaction.appKey },
      });
      const target = new URL(transaction.returnTo, canonicalAuthOrigin(req));
      target.searchParams.set("grant", handoff.code);
      res.redirect(303, target.toString());
      return;
    }
    await rotateSession(req, res, user.id);
    await audit({
      eventType: "lark.login",
      outcome: "success",
      userId: user.id,
      requestId: id,
    });
    if (transaction.interactionUid) {
      const interaction = await getOidcProvider().interactionDetails(req, res);
      if (interaction.uid !== transaction.interactionUid)
        throw new Error("OIDC_INTERACTION_MISMATCH");
      await finishInteraction(req, res, user.id);
      return;
    }
    res.redirect(303, transaction.returnTo ?? "/");
  } catch (error) {
    const reason =
      error instanceof Error && error.message.startsWith("LARK_")
        ? error.message
        : "login_failed";
    await audit({
      eventType: "lark.login",
      outcome: "failure",
      requestId: id,
      detail: { reason },
    }).catch(() => undefined);
    if (!res.headersSent) redirectError(res, reason.toLowerCase());
  }
}
