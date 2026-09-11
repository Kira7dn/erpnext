import Provider, { type Configuration, type JWKS } from "oidc-provider";

import { getDb } from "./db";
import { AUTH_FEATURE_CONFIG, getEnv, parseJsonEnv } from "./env";
import { PrismaOidcAdapter } from "./oidc-adapter";
import { audit } from "./audit";

type ProviderGlobal = typeof globalThis & { __letronOidcProvider?: Provider };

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char] ?? char);
}

export function getOidcProvider(): Provider {
  const globalScope = globalThis as ProviderGlobal;
  if (globalScope.__letronOidcProvider) return globalScope.__letronOidcProvider;
  const env = getEnv();
  const cookieKeys = parseJsonEnv<string[]>("OIDC_COOKIE_KEYS", env.OIDC_COOKIE_KEYS);
  const jwks = parseJsonEnv<JWKS>("OIDC_JWKS", env.OIDC_JWKS);
  if (!Array.isArray(cookieKeys) || cookieKeys.length < 2 || cookieKeys.some((key) => key.length < 32)) {
    throw new Error("OIDC_COOKIE_KEYS must be a JSON array containing at least two 32-character keys");
  }
  if (!Array.isArray(jwks.keys) || jwks.keys.length === 0) throw new Error("OIDC_JWKS must contain a private signing key");

  const configuration: Configuration = {
    adapter: PrismaOidcAdapter,
    jwks,
    scopes: ["openid", "profile", "email", "groups"],
    claims: {
      openid: ["sub"],
      profile: ["name", "picture"],
      email: ["email", "email_verified"],
      groups: [
        "groups",
        "lark_tenant_key",
        "lark_subject",
        "lark_subject_type",
        "lark_groups_synced_at",
      ],
    },
    responseTypes: ["code"],
    clientAuthMethods: ["none", "client_secret_basic"],
    pkce: { required: () => true },
    subjectTypes: ["public"],
    conformIdTokenClaims: false,
    acceptQueryParamAccessTokens: false,
    allowOmittingSingleRegisteredRedirectUri: false,
    cookies: {
      keys: cookieKeys,
      names: {
        session: "letron_oidc_session",
        interaction: "letron_oidc_interaction",
        resume: "letron_oidc_resume",
      },
      long: { httpOnly: true, sameSite: "lax", secure: env.LETRON_AUTH_BASE_URL.startsWith("https://"), path: "/" },
      short: { httpOnly: true, sameSite: "lax", secure: env.LETRON_AUTH_BASE_URL.startsWith("https://"), path: "/" },
    },
    ttl: {
      AccessToken: 10 * 60,
      AuthorizationCode: 60,
      IdToken: 10 * 60,
      Interaction: 10 * 60,
      Session: AUTH_FEATURE_CONFIG.sessionTtlSeconds,
    },
    interactions: {
      url: (_ctx, interaction) => `/login?uid=${encodeURIComponent(interaction.uid)}`,
    },
    features: {
      devInteractions: { enabled: false },
      claimsParameter: { enabled: false },
      clientCredentials: { enabled: false },
      registration: { enabled: false },
      deviceFlow: { enabled: false },
      introspection: { enabled: false },
      revocation: { enabled: false },
      userinfo: { enabled: true },
      rpInitiatedLogout: {
        enabled: true,
        logoutSource: (ctx, form) => {
          ctx.type = "html";
          ctx.body = `<!doctype html><html lang="vi"><meta charset="utf-8"><title>Đăng xuất</title><body>${form}<p>Đang đăng xuất…</p><script>document.getElementById("op.logoutForm").submit()</script></body></html>`;
        },
        postLogoutSuccessSource: (ctx) => {
          ctx.redirect("/");
        },
      },
    },
    findAccount: async (_ctx, accountId) => {
      const user = await getDb().user.findUnique({
        where: { id: accountId },
        include: {
          identities: {
            where: { provider: "lark" },
            orderBy: { id: "asc" },
            take: 1,
          },
        },
      });
      if (!user || user.status !== "ACTIVE") return undefined;
      const larkIdentity = user.identities[0];
      return {
        accountId: user.id,
        claims: async () => ({
          sub: user.id,
          name: user.displayName,
          email: user.email,
          email_verified: true,
          picture: user.avatarUrl ?? undefined,
          groups: larkIdentity?.groupIds ?? [],
          lark_tenant_key: larkIdentity?.tenantKey,
          lark_subject: larkIdentity?.subject,
          lark_subject_type: larkIdentity?.subjectType,
          lark_groups_synced_at: larkIdentity?.groupsSyncedAt?.toISOString(),
        }),
      };
    },
    renderError: (ctx, out) => {
      ctx.type = "html";
      ctx.status = 400;
      ctx.body = `<!doctype html><html lang="vi"><meta charset="utf-8"><title>SSO error</title><body><h1>Không thể tiếp tục đăng nhập</h1><p>${escapeHtml(out.error_description ?? out.error)}</p><a href="/login">Quay lại</a></body></html>`;
    },
  };

  const provider = new Provider(`${env.LETRON_AUTH_BASE_URL}/api/oidc`, configuration);
  provider.proxy = true;
  provider.on("authorization.success", (ctx) => {
    void audit({
      eventType: "oidc.authorization",
      outcome: "success",
      clientId: typeof ctx.oidc.params?.client_id === "string" ? ctx.oidc.params.client_id : undefined,
    }).catch(() => undefined);
  });
  provider.on("authorization.error", (ctx) => {
    void audit({
      eventType: "oidc.authorization",
      outcome: "failure",
      clientId: typeof ctx.oidc.params?.client_id === "string" ? ctx.oidc.params.client_id : undefined,
    }).catch(() => undefined);
  });
  globalScope.__letronOidcProvider = provider;
  return provider;
}

export function resetOidcProviderForTests(): void {
  delete (globalThis as ProviderGlobal).__letronOidcProvider;
}
