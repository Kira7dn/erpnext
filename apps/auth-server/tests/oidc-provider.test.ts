import { createServer } from "node:http";
import type { AddressInfo } from "node:net";

import { exportJWK, generateKeyPair } from "jose";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { resetEnvForTests } from "../src/server/env";
import { getOidcProvider, resetOidcProviderForTests } from "../src/server/oidc";

beforeEach(async () => {
  const { privateKey } = await generateKeyPair("RS256", { extractable: true, modulusLength: 2048 });
  const jwk = await exportJWK(privateKey);
  Object.assign(jwk, { alg: "RS256", use: "sig", kid: "test-key" });
  Object.assign(process.env, {
    AUTH_BASE_URL: "http://localhost:3000",
    DATABASE_URL: "postgresql://test:test@localhost/test",
    LARK_APP_ID: "cli_test",
    LARK_APP_SECRET: "secret",
    LARK_ALLOWED_TENANT_KEY: "tenant-test",
    AUTH_DATA_ENCRYPTION_KEY: Buffer.alloc(32, 3).toString("base64"),
    OIDC_COOKIE_KEYS: JSON.stringify(["a".repeat(32), "b".repeat(32)]),
    OIDC_JWKS: JSON.stringify({ keys: [jwk] }),
    NODE_ENV: "test",
  });
  resetEnvForTests();
  resetOidcProviderForTests();
});

afterEach(() => {
  resetOidcProviderForTests();
  resetEnvForTests();
});

describe("serverless OIDC mount", () => {
  it("serves a valid discovery document through a prefix-stripping Next-style handler", async () => {
    const provider = getOidcProvider();
    const callback = provider.callback();
    const server = createServer(async (req, res) => {
      (req as typeof req & { originalUrl?: string }).originalUrl = req.url;
      req.headers["x-forwarded-host"] = "localhost:3000";
      req.headers["x-forwarded-proto"] = "http";
      req.url = (req.url ?? "/").replace(/^\/api\/oidc/, "") || "/";
      await callback(req, res);
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));

    try {
      const { port } = server.address() as AddressInfo;
      const response = await fetch(`http://127.0.0.1:${port}/api/oidc/.well-known/openid-configuration`);
      const discovery = await response.json() as Record<string, unknown>;
      expect(response.status).toBe(200);
      expect(discovery.issuer).toBe("http://localhost:3000/api/oidc");
      expect(discovery.authorization_endpoint).toBe("http://localhost:3000/api/oidc/auth");
      expect(discovery.token_endpoint).toBe("http://localhost:3000/api/oidc/token");
      expect(discovery.response_types_supported).toEqual(["code"]);
      expect(discovery.code_challenge_methods_supported).toEqual(["S256"]);
      expect(discovery.scopes_supported).toEqual(expect.arrayContaining(["openid", "profile", "email", "groups"]));
      expect(discovery.claims_supported).toEqual(expect.arrayContaining([
        "groups",
        "lark_tenant_key",
        "lark_subject",
        "lark_subject_type",
        "lark_groups_synced_at",
      ]));
      expect(discovery.registration_endpoint).toBeUndefined();
      expect(discovery.device_authorization_endpoint).toBeUndefined();
    } finally {
      await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
    }
  });
});
