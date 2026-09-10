import "server-only";

import { createCipheriv, createDecipheriv, createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { Redis } from "@upstash/redis";
import { cookies } from "next/headers";
import { ApiRequestError } from "./api-error";
import { supplierPortalConfig } from "./supplier-portal-config";

const ACCESS_TTL_SECONDS = 90 * 24 * 60 * 60;
const OTP_TTL_SECONDS = 5 * 60;
const SESSION_TTL_SECONDS = 2 * 60 * 60;
const OTP_RESEND_COOLDOWN_SECONDS = 15;
const SESSION_COOKIE = "letron_supplier_session";

export type SupplierPortalAccess = {
  access_id: string;
  orchestration_id: string;
  material_request: string;
  supplier: string;
  email: string;
  request_for_quotation: string;
  magic_token_hash: string;
  encrypted_magic_token?: string;
  magic_expires_at: string;
  quotation_deadline_at?: string;
  otp_hash?: string;
  otp_expires_at?: number;
  otp_attempts?: number;
  otp_sent_at?: number;
};

type SupplierPortalSession = { access_id: string; session_hash: string };
let client: Redis | undefined;

function store(): Redis {
  if (client) return client;
  const url = process.env.KV_REST_API_URL;
  const token = process.env.KV_REST_API_TOKEN;
  if (!url || !token) throw new ApiRequestError("configuration_error", "Supplier portal storage is not configured.", 503);
  client = new Redis({ url, token });
  return client;
}

function hash(value: string): string { return createHash("sha256").update(value).digest("hex"); }
function tokenKeyMaterial(): Buffer {
  const secret = process.env.LETRON_SSO_SYNC_SECRET?.trim();
  if (!secret) throw new ApiRequestError("configuration_error", "Supplier portal token protection is not configured.", 503);
  return createHash("sha256").update(secret).digest();
}
function encryptToken(value: string): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", tokenKeyMaterial(), iv);
  const ciphertext = Buffer.concat([cipher.update(value, "utf8"), cipher.final()]);
  return `${iv.toString("base64url")}.${cipher.getAuthTag().toString("base64url")}.${ciphertext.toString("base64url")}`;
}
export function decryptSupplierPortalToken(access: SupplierPortalAccess): string {
  if (!access.encrypted_magic_token) throw new ApiRequestError("supplier_portal_access_denied", "Magic Link is invalid or expired.", 403);
  const [ivText, tagText, ciphertextText] = access.encrypted_magic_token.split(".");
  const decipher = createDecipheriv("aes-256-gcm", tokenKeyMaterial(), Buffer.from(ivText, "base64url"));
  decipher.setAuthTag(Buffer.from(tagText, "base64url"));
  return Buffer.concat([decipher.update(Buffer.from(ciphertextText, "base64url")), decipher.final()]).toString("utf8");
}
function accessKey(id: string): string { return `erp:supplier-portal:access-id:${id}`; }
function orchestrationKey(id: string): string { return `erp:supplier-portal:orchestration:${id}`; }
function tokenKey(token: string): string { return `erp:supplier-portal:token:${hash(token)}`; }
function sessionKey(token: string): string { return `erp:supplier-portal:session:${hash(token)}`; }
function lockKey(id: string): string { return `erp:supplier-portal:lock:${id}`; }
function newToken(): string { return randomBytes(32).toString("base64url"); }
function now(): number { return Math.floor(Date.now() / 1000); }

export function newSupplierPortalToken(): string { return newToken(); }

export async function getAccessById(accessId: string): Promise<SupplierPortalAccess | null> {
  return await store().get<SupplierPortalAccess>(accessKey(accessId));
}

export async function registerAccess(input: Omit<SupplierPortalAccess, "magic_token_hash"> & { magic_token: string }): Promise<SupplierPortalAccess> {
  const access: SupplierPortalAccess = { ...input, magic_token_hash: hash(input.magic_token), encrypted_magic_token: encryptToken(input.magic_token) };
  const db = store();
  await db.set(accessKey(access.access_id), access, { ex: ACCESS_TTL_SECONDS });
  await db.set(tokenKey(input.magic_token), access.access_id, { ex: ACCESS_TTL_SECONDS });
  return access;
}

export async function registerAccessForOrchestration(orchestrationId: string, access: Omit<SupplierPortalAccess, "magic_token_hash"> & { magic_token: string }): Promise<SupplierPortalAccess> {
  const db = store();
  const existingId = await db.hget<string>(orchestrationKey(orchestrationId), access.supplier);
  if (existingId) {
    const existing = await getAccessById(existingId);
    if (existing) return existing;
  }
  const lock = await db.set(`${orchestrationKey(orchestrationId)}:lock:${hash(access.supplier)}`, "1", { nx: true, ex: 15 });
  if (!lock) {
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const winnerId = await db.hget<string>(orchestrationKey(orchestrationId), access.supplier);
      if (winnerId) {
        const winner = await getAccessById(winnerId);
        if (winner) return winner;
      }
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new ApiRequestError("supplier_portal_request_rejected", "Supplier access could not be claimed.", 409, true);
  }
  const created = await registerAccess(access);
  await db.hset(orchestrationKey(orchestrationId), { [access.supplier]: created.access_id });
  await db.expire(orchestrationKey(orchestrationId), ACCESS_TTL_SECONDS);
  return created;
}

export async function getAccessesForOrchestration(orchestrationId: string): Promise<SupplierPortalAccess[]> {
  const ids = await store().hgetall<Record<string, string>>(orchestrationKey(orchestrationId));
  if (!ids) return [];
  const values = await Promise.all(Object.values(ids).map((id) => getAccessById(id)));
  return values.filter((value): value is SupplierPortalAccess => Boolean(value));
}

export async function updateAccess(access: SupplierPortalAccess): Promise<void> {
  await store().set(accessKey(access.access_id), access, { ex: ACCESS_TTL_SECONDS });
}

export async function getAccessByMagicToken(token: string): Promise<SupplierPortalAccess> {
  const accessId = await store().get<string>(tokenKey(token));
  if (!accessId) throw new ApiRequestError("supplier_portal_not_found", "Magic Link is invalid or expired.", 404);
  const access = await getAccessById(accessId);
  const suppliedHash = Buffer.from(hash(token), "utf8");
  const storedHash = access?.magic_token_hash ? Buffer.from(access.magic_token_hash, "utf8") : Buffer.alloc(0);
  const tokenMatches = suppliedHash.length === storedHash.length && timingSafeEqual(suppliedHash, storedHash);
  if (!access || !tokenMatches || access.magic_expires_at && Date.parse(access.magic_expires_at) <= Date.now()) {
    throw new ApiRequestError("supplier_portal_access_denied", "Magic Link is invalid or expired.", 403);
  }
  return access;
}

export function buildAccessMail(access: SupplierPortalAccess, magicToken: string): { to: string; subject: string; body_html: string; body_plain_text: string; idempotency_key: string } {
  const portalUrl = `${supplierPortalConfig().portal_public_base_url.replace(/\/$/, "")}/supplier/${magicToken}`;
  const plain = [
    `Supplier: ${access.supplier}`,
    `RFQ: ${access.request_for_quotation}`,
    `Expires: ${access.magic_expires_at}`,
    "Do not share this link or OTP with anyone.",
    `Open this Magic Link and request an OTP: ${portalUrl}`,
  ].join("\n");
  return { to: access.email, subject: "Letron Supplier Portal access", body_html: `<p>${plain.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\n/g, "<br>")}</p>`, body_plain_text: plain, idempotency_key: `supplier-access:${access.access_id}` };
}

export function buildOtpMail(access: SupplierPortalAccess, otp: string): { to: string; subject: string; body_html: string; body_plain_text: string; idempotency_key: string } {
  const plain = [`Supplier: ${access.supplier}`, `RFQ: ${access.request_for_quotation}`, `OTP: ${otp}`, "Do not share this OTP with anyone."].join("\n");
  return { to: access.email, subject: "Letron Supplier Portal OTP", body_html: `<p>${plain.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\n/g, "<br>")}</p>`, body_plain_text: plain, idempotency_key: `supplier-otp:${access.access_id}:${Math.floor(Date.now() / 1000)}` };
}

export async function requestNextOtp(magicToken: string): Promise<{ access: SupplierPortalAccess; otp: string }> {
  const access = await getAccessByMagicToken(magicToken);
  const db = store();
  const lock = await db.set(lockKey(access.access_id), "1", { nx: true, ex: 10 });
  if (!lock) throw new ApiRequestError("supplier_portal_rate_limited", "Supplier Portal request is temporarily limited.", 429, true, 10);
  const current = await getAccessById(access.access_id) ?? access;
  const currentTime = now();
  if (current.otp_sent_at && currentTime - current.otp_sent_at < OTP_RESEND_COOLDOWN_SECONDS) {
    const retry = OTP_RESEND_COOLDOWN_SECONDS - (currentTime - current.otp_sent_at);
    throw new ApiRequestError("supplier_otp_rate_limited", "OTP request is temporarily limited.", 429, true, retry);
  }
  const otp = String(Math.floor(Math.random() * 1_000_000)).padStart(6, "0");
  const updated = { ...current, otp_hash: hash(otp), otp_expires_at: Date.now() + OTP_TTL_SECONDS * 1000, otp_attempts: 0, otp_sent_at: currentTime };
  await db.set(accessKey(current.access_id), updated, { ex: ACCESS_TTL_SECONDS });
  return { access: updated, otp };
}

export async function verifyNextOtp(magicToken: string, otp: string): Promise<{ sessionToken: string; expiresInSeconds: number }> {
  const access = await getAccessByMagicToken(magicToken);
  const db = store();
  const lock = await db.set(lockKey(access.access_id), "1", { nx: true, ex: 10 });
  if (!lock) throw new ApiRequestError("supplier_portal_rate_limited", "Supplier Portal request is temporarily limited.", 429, true, 10);
  const current = await getAccessById(access.access_id) ?? access;
  const attempts = Number(current.otp_attempts ?? 0) + 1;
  if (!current.otp_hash || !current.otp_expires_at || current.otp_expires_at <= Date.now() || attempts > 5 || hash(otp) !== current.otp_hash) {
    await db.set(accessKey(current.access_id), { ...current, otp_attempts: attempts }, { ex: ACCESS_TTL_SECONDS });
    throw new ApiRequestError("otp_invalid_or_expired", "OTP is invalid or expired.", 401);
  }
  const sessionToken = newToken();
  const session: SupplierPortalSession = { access_id: current.access_id, session_hash: hash(sessionToken) };
  await db.set(sessionKey(sessionToken), session, { ex: SESSION_TTL_SECONDS });
  await db.set(accessKey(current.access_id), { ...current, otp_hash: undefined, otp_expires_at: undefined, otp_attempts: 0 }, { ex: ACCESS_TTL_SECONDS });
  return { sessionToken, expiresInSeconds: SESSION_TTL_SECONDS };
}

export async function getSupplierPortalSession(): Promise<{ sessionToken: string; access: SupplierPortalAccess } | null> {
  const sessionToken = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!sessionToken) return null;
  const session = await store().get<SupplierPortalSession>(sessionKey(sessionToken));
  if (!session) return null;
  const access = await getAccessById(session.access_id);
  if (!access) return null;
  return { sessionToken, access };
}

export async function clearSupplierPortalSession(): Promise<void> {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (token) await store().del(sessionKey(token));
  jar.delete(SESSION_COOKIE);
}

export const SUPPLIER_SESSION_COOKIE = SESSION_COOKIE;
