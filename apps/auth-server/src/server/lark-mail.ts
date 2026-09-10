import { z } from "zod";

import { decrypt, encrypt, sha256 } from "./crypto";
import { getDb } from "./db";
import { getEnv } from "./env";
import { fetchLarkIdentity } from "./lark";

const exchangeTokenSchema = z.object({
  access_token: z.string().min(1),
  refresh_token: z.string().min(1),
  expires_in: z.number().int().positive().optional(),
  refresh_token_expires_in: z.number().int().positive().optional(),
  scope: z.string().optional(),
});

const refreshTokenSchema = z.object({
  access_token: z.string().min(1),
  refresh_token: z.string().min(1).optional(),
  expires_in: z.number().int().positive().optional(),
  refresh_token_expires_in: z.number().int().positive().optional(),
  scope: z.string().optional(),
});

const appTokenSchema = z.object({ app_access_token: z.string().min(1) });

export const LARK_PUBLIC_MAILBOX = "procurement@letrongroup.com";

function unwrap(value: unknown): unknown {
  if (value && typeof value === "object" && "data" in value) return (value as { data: unknown }).data;
  return value;
}

async function json(response: Response): Promise<unknown> {
  const payload = await response.json();
  if (!response.ok || (payload && typeof payload === "object" && "code" in payload && payload.code !== 0)) {
    const code = payload && typeof payload === "object" && "code" in payload ? String(payload.code) : String(response.status);
    const msg = payload && typeof payload === "object" && "msg" in payload ? String(payload.msg) : "request failed";
    throw new Error(`LARK_MAIL_${code}: ${msg}`);
  }
  return payload;
}

export const LARK_MAIL_OAUTH_COOKIE = "letron_lark_mail_oauth";
export const LARK_MAIL_OAUTH_TTL_SECONDS = 600;

export function larkMailCallbackUri(origin = getEnv().AUTH_BASE_URL): string {
  // Reuse the already-whitelisted Lark SSO callback. The callback dispatches
  // to the mail transaction when the mail OAuth cookie/state is present.
  return `${origin.replace(/\/$/, "")}/api/auth/lark/callback`;
}

export function buildLarkMailAuthorizationUrl(state: string, redirectUri = larkMailCallbackUri()): URL {
  const env = getEnv();
  const url = new URL("/open-apis/authen/v1/authorize", env.LARK_DOMAIN);
  url.searchParams.set("client_id", env.LARK_APP_ID);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("redirect_uri", redirectUri);
  url.searchParams.set("state", state);
  url.searchParams.set("scope", [
    "mail:user_mailbox.message:send",
    "mail:user_mailbox.message:readonly",
    "mail:user_mailbox.message.address:read",
    "mail:user_mailbox.message.body:read",
    "mail:user_mailbox.message.subject:read",
  ].join(" "));
  return url;
}

export async function completeLarkMailOAuth(input: { state: string; binding: string; code: string }): Promise<string> {
  const consumed = await getDb().$transaction(async (tx) => {
    const row = await tx.larkMailOAuthTransaction.findUnique({ where: { stateHash: sha256(input.state) } });
    if (!row || row.consumedAt || row.expiresAt.getTime() <= Date.now() || row.browserBindingHash !== sha256(input.binding)) return false;
    const updated = await tx.larkMailOAuthTransaction.updateMany({ where: { id: row.id, consumedAt: null }, data: { consumedAt: new Date() } });
    return updated.count === 1;
  });
  if (!consumed) throw new Error("MAIL_OAUTH_TRANSACTION_INVALID");
  const token = await exchangeLarkMailCode(input.code);
  const identity = await fetchLarkIdentity(token.access_token);
  const expectedMailbox = getEnv().LARK_PO_APPROVER_EMAIL?.toLowerCase();
  if (!expectedMailbox || identity.email.toLowerCase() !== expectedMailbox) throw new Error("LARK_MAIL_MAILBOX_MISMATCH");
  await saveLarkMailCredential({
    mailboxEmail: LARK_PUBLIC_MAILBOX,
    tenantKey: identity.tenantKey,
    subject: identity.subject,
    refreshToken: token.refresh_token,
    refreshTokenExpiresIn: token.refresh_token_expires_in,
    scope: token.scope,
  });
  return expectedMailbox;
}

async function appAccessToken(): Promise<string> {
  const env = getEnv();
  const response = await fetch(new URL("/open-apis/auth/v3/app_access_token/internal", env.LARK_DOMAIN), {
    method: "POST",
    headers: { "content-type": "application/json; charset=utf-8" },
    body: JSON.stringify({ app_id: env.LARK_APP_ID, app_secret: env.LARK_APP_SECRET }),
    signal: AbortSignal.timeout(10_000),
  });
  return appTokenSchema.parse(unwrap(await json(response))).app_access_token;
}

export async function exchangeLarkMailCode(code: string): Promise<z.infer<typeof exchangeTokenSchema>> {
  const env = getEnv();
  const response = await fetch(new URL("/open-apis/authen/v1/access_token", env.LARK_DOMAIN), {
    method: "POST",
    headers: { authorization: `Bearer ${await appAccessToken()}`, "content-type": "application/json; charset=utf-8" },
    body: JSON.stringify({ grant_type: "authorization_code", code }),
    signal: AbortSignal.timeout(10_000),
  });
  return exchangeTokenSchema.parse(unwrap(await json(response)));
}

async function refreshLarkMailToken(refreshToken: string): Promise<z.infer<typeof refreshTokenSchema>> {
  const env = getEnv();
  const response = await fetch(new URL("/open-apis/authen/v1/refresh_access_token", env.LARK_DOMAIN), {
    method: "POST",
    headers: { authorization: `Bearer ${await appAccessToken()}`, "content-type": "application/json; charset=utf-8" },
    body: JSON.stringify({ grant_type: "refresh_token", refresh_token: refreshToken }),
    signal: AbortSignal.timeout(10_000),
  });
  return refreshTokenSchema.parse(unwrap(await json(response)));
}

export async function saveLarkMailCredential(input: {
  mailboxEmail: string;
  tenantKey: string;
  subject: string;
  refreshToken: string;
  refreshTokenExpiresIn?: number;
  scope?: string;
}): Promise<void> {
  await getDb().larkMailCredential.upsert({
    where: { mailboxEmail: input.mailboxEmail.toLowerCase() },
    create: {
      mailboxEmail: input.mailboxEmail.toLowerCase(),
      tenantKey: input.tenantKey,
      subject: input.subject,
      encryptedRefreshToken: encrypt(input.refreshToken),
      refreshTokenExpiresAt: input.refreshTokenExpiresIn ? new Date(Date.now() + input.refreshTokenExpiresIn * 1000) : undefined,
      grantedScopes: input.scope,
    },
    update: {
      tenantKey: input.tenantKey,
      subject: input.subject,
      encryptedRefreshToken: encrypt(input.refreshToken),
      refreshTokenExpiresAt: input.refreshTokenExpiresIn ? new Date(Date.now() + input.refreshTokenExpiresIn * 1000) : undefined,
      grantedScopes: input.scope,
    },
  });
}

async function refreshStoredLarkMailCredential(mailboxEmail: string): Promise<string> {
  return getDb().$transaction(async (tx) => {
    await tx.$executeRawUnsafe(
      "SELECT pg_advisory_xact_lock(hashtext($1))",
      `letron:lark-mail-refresh:${mailboxEmail.toLowerCase()}`,
    );
    const credential = await tx.larkMailCredential.findUnique({ where: { mailboxEmail } });
    if (!credential) throw new Error("LARK_MAIL_OAUTH_REQUIRED");
    const token = await refreshLarkMailToken(decrypt(credential.encryptedRefreshToken));
    if (token.refresh_token) {
      await tx.larkMailCredential.update({
        where: { id: credential.id },
        data: {
          encryptedRefreshToken: encrypt(token.refresh_token),
          refreshTokenExpiresAt: token.refresh_token_expires_in ? new Date(Date.now() + token.refresh_token_expires_in * 1000) : undefined,
          grantedScopes: token.scope ?? credential.grantedScopes ?? undefined,
        },
      });
    }
    return token.access_token;
  }, { maxWait: 10_000, timeout: 30_000 });
}

export async function sendLarkMail(input: { to: string; subject: string; bodyHtml: string; bodyPlainText?: string }): Promise<{ messageId: string }> {
  const mailboxEmail = LARK_PUBLIC_MAILBOX;
  const accessToken = await refreshStoredLarkMailCredential(mailboxEmail);
  const env = getEnv();
  const response = await fetch(new URL(`/open-apis/mail/v1/user_mailboxes/${encodeURIComponent(mailboxEmail)}/messages/send`, env.LARK_DOMAIN), {
    method: "POST",
    headers: { authorization: `Bearer ${accessToken}`, "content-type": "application/json; charset=utf-8" },
    body: JSON.stringify({
      subject: input.subject,
      to: [{ mail_address: input.to }],
      body_html: input.bodyHtml,
      body_plain_text: input.bodyPlainText ?? input.bodyHtml.replace(/<[^>]+>/g, ""),
    }),
    signal: AbortSignal.timeout(15_000),
  });
  const payload = await json(response) as { data?: { message_id?: string }; message_id?: string };
  const messageId = payload.data?.message_id ?? payload.message_id;
  if (!messageId) throw new Error("LARK_MAIL_MESSAGE_ID_MISSING");
  return { messageId };
}

export async function latestLarkMail(input: { subject: string; after?: string }): Promise<Array<{ subject: string; message: string; recipients: string; internalDate: string }>> {
  const accessToken = await refreshStoredLarkMailCredential(LARK_PUBLIC_MAILBOX);
  const env = getEnv();
  const mailbox = env.LARK_PO_APPROVER_EMAIL;
  if (!mailbox) throw new Error("LARK_MAIL_READER_NOT_CONFIGURED");
  const listUrl = new URL(`/open-apis/mail/v1/user_mailboxes/${encodeURIComponent(mailbox)}/messages`, env.LARK_DOMAIN);
  listUrl.searchParams.set("page_size", "20");
  listUrl.searchParams.set("folder_id", "INBOX");
  const listResponse = await fetch(listUrl, { headers: { authorization: `Bearer ${accessToken}` }, signal: AbortSignal.timeout(15_000) });
  const listed = await json(listResponse) as { data?: { items?: string[] } };
  const after = input.after ? Date.parse(input.after) : 0;
  const results: Array<{ subject: string; message: string; recipients: string; internalDate: string }> = [];
  for (const messageId of listed.data?.items ?? []) {
    const detailUrl = new URL(`/open-apis/mail/v1/user_mailboxes/${encodeURIComponent(mailbox)}/messages/${encodeURIComponent(messageId)}`, env.LARK_DOMAIN);
    detailUrl.searchParams.set("format", "full");
    const detailResponse = await fetch(detailUrl, { headers: { authorization: `Bearer ${accessToken}` }, signal: AbortSignal.timeout(15_000) });
    const detail = await json(detailResponse) as { data?: { message?: { subject?: string; body_plain_text?: string; internal_date?: string; to?: Array<{ mail_address?: string }> } } };
    const mail = detail.data?.message;
    if (!mail || mail.subject !== input.subject || (Number(mail.internal_date ?? 0) && Number(mail.internal_date) < after)) continue;
    const encoded = mail.body_plain_text ?? "";
    const message = encoded ? Buffer.from(encoded, "base64url").toString("utf8") : "";
    results.push({
      subject: mail.subject ?? "",
      message,
      recipients: (mail.to ?? []).map((item) => item.mail_address ?? "").filter(Boolean).join(","),
      internalDate: mail.internal_date ?? "",
    });
  }
  return results;
}
