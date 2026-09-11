import { NextRequest, NextResponse } from "next/server";

import { getEnv } from "../../../src/server/env";
import { pkceChallenge, randomToken } from "../../../src/server/crypto";
import { buildLarkAuthorizationUrl, larkCallbackUri } from "../../../src/server/lark";
import {
  LARK_TRANSACTION_COOKIE,
  LARK_TRANSACTION_TTL_SECONDS,
  saveOAuthTransaction,
} from "../../../src/server/oauth-transaction";
import type { AppKey } from "../../../src/server/erp-handoff";

export const dynamic = "force-dynamic";

function safeReturnTo(value: string | null): string {
  if (!value) return "/";
  if (value.startsWith("/") && !value.startsWith("//")) return value;

  try {
    const requested = new URL(value);
    const allowed = new URL(getEnv().LETRON_ERP_APP_BASE_URL);
    return requested.origin === allowed.origin ? requested.toString() : "/";
  } catch {
    return "/";
  }
}

function parseAppKey(value: string | null): AppKey | undefined {
  return value === "assets" || value === "purchase" || value === "accounts" ? value : undefined;
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  const requestId = request.headers.get("x-request-id") ?? crypto.randomUUID();

  try {
    const env = getEnv();
    const state = randomToken();
    const browserBinding = randomToken();
    const codeVerifier = randomToken(48);
    const redirectUri = larkCallbackUri(env.LETRON_AUTH_BASE_URL);
    const appKey = parseAppKey(request.nextUrl.searchParams.get("app"));

    await saveOAuthTransaction({
      state,
      browserBinding,
      codeVerifier,
      handoff: false,
      appKey,
      returnTo: safeReturnTo(request.nextUrl.searchParams.get("return_to")),
    });

    const response = NextResponse.redirect(
      buildLarkAuthorizationUrl({
        state,
        codeChallenge: pkceChallenge(codeVerifier),
        redirectUri,
      }).toString(),
      303,
    );
    response.cookies.set(LARK_TRANSACTION_COOKIE, browserBinding, {
      httpOnly: true,
      maxAge: LARK_TRANSACTION_TTL_SECONDS,
      path: "/",
      sameSite: "lax",
      secure: request.nextUrl.protocol === "https:",
    });
    response.headers.set("Cache-Control", "no-store");
    response.headers.set("X-Request-Id", requestId);
    return response;
  } catch {
    return NextResponse.json(
      { error: "login_start_failed", request_id: requestId },
      {
        headers: { "Cache-Control": "no-store", "X-Request-Id": requestId },
        status: 503,
      },
    );
  }
}
