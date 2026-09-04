import { beforeEach, describe, expect, it } from "vitest";

import { decrypt, encrypt, pkceChallenge, sha256 } from "../src/server/crypto";
import { resetEnvForTests } from "../src/server/env";

beforeEach(() => {
  Object.assign(process.env, {
    AUTH_BASE_URL: "http://localhost:3000",
    DATABASE_URL: "postgresql://test:test@localhost/test",
    LARK_APP_ID: "cli_test",
    LARK_APP_SECRET: "secret",
    LARK_ALLOWED_TENANT_KEY: "tenant-test",
    AUTH_DATA_ENCRYPTION_KEY: Buffer.alloc(32, 7).toString("base64"),
    OIDC_COOKIE_KEYS: JSON.stringify(["a".repeat(32), "b".repeat(32)]),
    OIDC_JWKS: JSON.stringify({ keys: [{ kty: "RSA" }] }),
  });
  resetEnvForTests();
});

describe("auth cryptography", () => {
  it("encrypts transaction secrets with authenticated encryption", () => {
    const encrypted = encrypt("verifier-value");
    expect(encrypted).not.toContain("verifier-value");
    expect(decrypt(encrypted)).toBe("verifier-value");
  });

  it("creates deterministic SHA-256 hashes and S256 PKCE challenges", () => {
    expect(sha256("abc")).toBe("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    expect(pkceChallenge("abc")).toBe("ungWv48Bz-pBQUDeXa4iI7ADYaOWF3qctBD_YfIAFa0");
  });
});
