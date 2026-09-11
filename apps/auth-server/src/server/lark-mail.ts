import { z } from "zod";

import { decrypt, encrypt, sha256 } from "./crypto";
import { getDb } from "./db";
import { getEnv } from "./env";
import { fetchLarkIdentity } from "./lark";
import { LARK_DOMAIN, LARK_PO_APPROVER_EMAIL } from "./lark-runtime-config";

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
const LARK_MAIL_SENDING_LEASE_MS = 60_000;
const LARK_MAIL_CONCURRENT_WAIT_MS = 20_000;

let cachedMailToken: { accessToken: string; expiresAt: number } | undefined;
let mailTokenRefresh: Promise<string> | undefined;

async function withTimeout<T>(operation: Promise<T>, milliseconds: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      operation,
      new Promise<T>((_, reject) => {
        timer = setTimeout(() => reject(new Error("LARK_MAIL_PROVIDER_TIMEOUT")), milliseconds);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function unwrap(value: unknown): unknown {
  if (!value || typeof value !== "object" || !("data" in value)) throw new Error("LARK_RESPONSE_DATA_MISSING");
  return (value as { data: unknown }).data;
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

export function larkMailCallbackUri(origin = getEnv().LETRON_AUTH_BASE_URL): string {
  // Reuse the already-whitelisted Lark SSO callback. The callback dispatches
  // to the mail transaction when the mail OAuth cookie/state is present.
  return `${origin.replace(/\/$/, "")}/api/auth/lark/callback`;
}

export function buildLarkMailAuthorizationUrl(state: string, redirectUri = larkMailCallbackUri()): URL {
  const env = getEnv();
  const url = new URL("/open-apis/authen/v1/authorize", LARK_DOMAIN);
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
  const expectedMailbox = LARK_PO_APPROVER_EMAIL?.toLowerCase();
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
  const response = await fetch(new URL("/open-apis/auth/v3/app_access_token/internal", LARK_DOMAIN), {
    method: "POST",
    headers: { "content-type": "application/json; charset=utf-8" },
    body: JSON.stringify({ app_id: env.LARK_APP_ID, app_secret: env.LARK_APP_SECRET }),
    signal: AbortSignal.timeout(10_000),
  });
  return appTokenSchema.parse(await json(response)).app_access_token;
}

export async function exchangeLarkMailCode(code: string): Promise<z.infer<typeof exchangeTokenSchema>> {
  const env = getEnv();
  const response = await fetch(new URL("/open-apis/authen/v1/access_token", LARK_DOMAIN), {
    method: "POST",
    headers: { authorization: `Bearer ${await appAccessToken()}`, "content-type": "application/json; charset=utf-8" },
    body: JSON.stringify({ grant_type: "authorization_code", code }),
    signal: AbortSignal.timeout(10_000),
  });
  return exchangeTokenSchema.parse(unwrap(await json(response)));
}

async function refreshLarkMailToken(refreshToken: string): Promise<z.infer<typeof refreshTokenSchema>> {
  const env = getEnv();
  const response = await fetch(new URL("/open-apis/authen/v1/refresh_access_token", LARK_DOMAIN), {
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
  if (cachedMailToken && cachedMailToken.expiresAt > Date.now() + 60_000) return cachedMailToken.accessToken;
  if (mailTokenRefresh) return mailTokenRefresh;
  mailTokenRefresh = (async () => {
    const db = getDb();
    const refreshed = await db.$transaction(async (tx) => {
      // Refresh tokens are rotated by Lark. Serialize refreshes across all
      // Next.js instances so two workers cannot consume the same token.
      await tx.$executeRawUnsafe("SELECT pg_advisory_xact_lock(hashtext($1))", `letron:lark-mail-refresh:${mailboxEmail.toLowerCase()}`);
      const credential = await tx.larkMailCredential.findUnique({ where: { mailboxEmail: mailboxEmail.toLowerCase() } });
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
      return { accessToken: token.access_token, expiresAt: Date.now() + (token.expires_in ?? 3600) * 1000 };
    }, { maxWait: 10_000, timeout: 30_000 });
    cachedMailToken = refreshed;
    return refreshed.accessToken;
  })();
  try { return await mailTokenRefresh; } finally { mailTokenRefresh = undefined; }
}

function invalidateCachedMailToken(): void {
  cachedMailToken = undefined;
}

export async function sendLarkMail(input: { to: string; subject: string; bodyHtml: string; bodyPlainText?: string; idempotencyKey: string }): Promise<{ messageId: string; idempotent?: boolean }> {
  const db = getDb();
  let delivery = await db.larkMailDelivery.findUnique({ where: { idempotencyKey: input.idempotencyKey } });
  let newlyClaimed = false;
  if (!delivery) {
    try {
      delivery = await db.larkMailDelivery.create({ data: { idempotencyKey: input.idempotencyKey, recipient: input.to, subject: input.subject, status: "SENDING" } });
      newlyClaimed = true;
    } catch (error) {
      // Another request may have claimed the same key between find and create.
      // Re-read the unique row so retries remain idempotent instead of leaking
      // a Prisma unique-constraint error to the caller.
      const concurrent = await db.larkMailDelivery.findUnique({ where: { idempotencyKey: input.idempotencyKey } });
      if (!concurrent) throw error;
      delivery = concurrent;
    }
  }
  if (delivery.status === "SENT" && delivery.providerMessageId) return { messageId: delivery.providerMessageId, idempotent: true };
  if (!newlyClaimed && delivery.status === "SENDING" && delivery.updatedAt.getTime() > Date.now() - LARK_MAIL_SENDING_LEASE_MS) {
    const deadline = Date.now() + LARK_MAIL_CONCURRENT_WAIT_MS;
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 500));
      const current = await db.larkMailDelivery.findUnique({ where: { id: delivery.id } });
      if (current?.status === "SENT" && current.providerMessageId) return { messageId: current.providerMessageId, idempotent: true };
      if (!current || current.status !== "SENDING") {
        delivery = current ?? delivery;
        break;
      }
    }
    if (delivery.status === "SENDING" && delivery.updatedAt.getTime() > Date.now() - LARK_MAIL_SENDING_LEASE_MS) throw new Error("LARK_MAIL_SEND_IN_PROGRESS");
  }
  if (!newlyClaimed) {
    const claimed = await db.larkMailDelivery.updateMany({
      where: {
        id: delivery.id,
        OR: [
          { status: "FAILED" },
          { status: "SENDING", updatedAt: { lte: new Date(Date.now() - LARK_MAIL_SENDING_LEASE_MS) } },
        ],
      },
      data: { recipient: input.to, subject: input.subject, status: "SENDING", lastError: null },
    });
    if (claimed.count !== 1) {
      const current = await db.larkMailDelivery.findUnique({ where: { id: delivery.id } });
      if (current?.status === "SENT" && current.providerMessageId) return { messageId: current.providerMessageId, idempotent: true };
      throw new Error("LARK_MAIL_SEND_IN_PROGRESS");
    }
    delivery = await db.larkMailDelivery.findUniqueOrThrow({ where: { id: delivery.id } });
  }
  const mailboxEmail = LARK_PUBLIC_MAILBOX;
  try {
    const env = getEnv();
    const messageId = await db.$transaction(async (tx) => {
      // Lark serializes send requests per mailbox. The transaction advisory
      // lock keeps that invariant across concurrent Next.js instances.
      await tx.$executeRawUnsafe("SELECT pg_advisory_xact_lock(hashtext($1))", `letron:lark-mail-send:${mailboxEmail.toLowerCase()}`);
      let payload: { data?: { message_id?: string }; message_id?: string } = {};
      for (let attempt = 0; attempt < 2; attempt += 1) {
        const accessToken = await refreshStoredLarkMailCredential(mailboxEmail);
        try {
          payload = await withTimeout((async () => {
            const response = await fetch(new URL(`/open-apis/mail/v1/user_mailboxes/${encodeURIComponent(mailboxEmail)}/messages/send`, LARK_DOMAIN), {
              method: "POST",
              headers: { authorization: `Bearer ${accessToken}`, "content-type": "application/json; charset=utf-8" },
              body: JSON.stringify({ subject: input.subject, to: [{ mail_address: input.to }], body_html: input.bodyHtml, body_plain_text: input.bodyPlainText ?? input.bodyHtml.replace(/<[^>]+>/g, ""), dedupe_key: input.idempotencyKey }),
              signal: AbortSignal.timeout(15_000),
            });
            return await json(response) as { data?: { message_id?: string }; message_id?: string };
          })(), 15_000);
          break;
        } catch (error) {
          if (attempt === 0 && error instanceof Error && error.message.startsWith("LARK_MAIL_99991668:")) {
            invalidateCachedMailToken();
            continue;
          }
          throw error;
        }
      }
      const providerMessageId = payload.data?.message_id;
      if (!providerMessageId) throw new Error("LARK_MAIL_MESSAGE_ID_MISSING");
      await tx.larkMailDelivery.update({ where: { id: delivery.id }, data: { status: "SENT", providerMessageId, sentAt: new Date(), lastError: null } });
      return providerMessageId;
    }, { maxWait: 10_000, timeout: 30_000 });
    return { messageId };
  } catch (error) {
    await db.larkMailDelivery.update({ where: { id: delivery.id }, data: { status: "FAILED", lastError: error instanceof Error ? error.message.slice(0, 500) : "mail_send_failed" } }).catch(() => undefined);
    throw error;
  }
}

export async function latestLarkMail(input: { subject: string; after?: string; messageId?: string }): Promise<Array<{ messageId: string; subject: string; message: string; recipients: string; internalDate: string }>> {
  const read = async (accessToken: string): Promise<Array<{ messageId: string; subject: string; message: string; recipients: string; internalDate: string }>> => {
    const env = getEnv();
    const mailbox = LARK_PO_APPROVER_EMAIL;
    if (!mailbox) throw new Error("LARK_MAIL_READER_NOT_CONFIGURED");
    const listUrl = new URL(`/open-apis/mail/v1/user_mailboxes/${encodeURIComponent(mailbox)}/messages`, LARK_DOMAIN);
    listUrl.searchParams.set("page_size", "20");
    listUrl.searchParams.set("folder_id", "INBOX");
    const listResponse = await fetch(listUrl, { headers: { authorization: `Bearer ${accessToken}` }, signal: AbortSignal.timeout(15_000) });
    const listed = await json(listResponse) as { data?: { items?: string[] } };
    const after = input.after ? Date.parse(input.after) : 0;
    const results: Array<{ messageId: string; subject: string; message: string; recipients: string; internalDate: string }> = [];
    const listedIds = listed.data?.items ?? [];
    const messageIds = input.messageId && listedIds.includes(input.messageId)
      ? [input.messageId]
      : listedIds.slice(0, 50);
    const concurrency = 8;
    for (let offset = 0; offset < messageIds.length; offset += concurrency) {
      const batch = messageIds.slice(offset, offset + concurrency);
      const details = await Promise.allSettled(batch.map(async (messageId) => {
      const detailUrl = new URL(`/open-apis/mail/v1/user_mailboxes/${encodeURIComponent(mailbox)}/messages/${encodeURIComponent(messageId)}`, LARK_DOMAIN);
      detailUrl.searchParams.set("format", "full");
      const detailResponse = await fetch(detailUrl, { headers: { authorization: `Bearer ${accessToken}` }, signal: AbortSignal.timeout(15_000) });
      const detail = await json(detailResponse) as { data?: { message?: { subject?: string; body_plain_text?: string; internal_date?: string; to?: Array<{ mail_address?: string }> } } };
      const mail = detail.data?.message;
      if (!mail || mail.subject !== input.subject || (Number(mail.internal_date ?? 0) && Number(mail.internal_date) < after)) return undefined;
      const encoded = mail.body_plain_text ?? "";
      const message = encoded ? Buffer.from(encoded, "base64url").toString("utf8") : "";
      return {
        messageId,
        subject: mail.subject ?? "",
        message,
        recipients: (mail.to ?? []).map((item) => item.mail_address ?? "").filter(Boolean).join(","),
        internalDate: mail.internal_date ?? "",
      };
      }));
      for (const detail of details) if (detail.status === "fulfilled" && detail.value) results.push(detail.value);
    }
    return results;
  };
  try {
    return await read(await refreshStoredLarkMailCredential(LARK_PUBLIC_MAILBOX));
  } catch (error) {
    if (!(error instanceof Error) || !error.message.startsWith("LARK_MAIL_99991668:")) throw error;
    invalidateCachedMailToken();
    return read(await refreshStoredLarkMailCredential(LARK_PUBLIC_MAILBOX));
  }
}
