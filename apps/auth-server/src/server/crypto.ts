import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";

import { getEnv } from "./env";

export function randomToken(bytes = 32): string {
  return randomBytes(bytes).toString("base64url");
}

export function sha256(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

export function pkceChallenge(verifier: string): string {
  return createHash("sha256").update(verifier, "ascii").digest("base64url");
}

function encryptionKey(): Buffer {
  const key = Buffer.from(getEnv().AUTH_DATA_ENCRYPTION_KEY, "base64");
  if (key.length !== 32) throw new Error("AUTH_DATA_ENCRYPTION_KEY must decode to exactly 32 bytes");
  return key;
}

export function encrypt(value: string): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", encryptionKey(), iv);
  const ciphertext = Buffer.concat([cipher.update(value, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return [iv, tag, ciphertext].map((part) => part.toString("base64url")).join(".");
}

export function decrypt(value: string): string {
  const [ivPart, tagPart, ciphertextPart, extra] = value.split(".");
  if (!ivPart || !tagPart || !ciphertextPart || extra) throw new Error("Invalid encrypted value");
  const decipher = createDecipheriv("aes-256-gcm", encryptionKey(), Buffer.from(ivPart, "base64url"));
  decipher.setAuthTag(Buffer.from(tagPart, "base64url"));
  return Buffer.concat([
    decipher.update(Buffer.from(ciphertextPart, "base64url")),
    decipher.final(),
  ]).toString("utf8");
}
