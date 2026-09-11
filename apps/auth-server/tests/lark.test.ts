import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetEnvForTests } from "../src/server/env";
import { canonicalAuthOrigin } from "../src/server/auth-origin";
import {
  buildLarkAuthorizationUrl,
  fetchLarkIdentity,
  fetchLarkGroupIds,
  LARK_LOGIN_SCOPES,
  resetLarkTokenCacheForTests,
} from "../src/server/lark";

beforeEach(() => {
  Object.assign(process.env, {
    LETRON_AUTH_BASE_URL: "http://localhost:3000",
    DATABASE_URL: "postgresql://test:test@localhost/test",
    LARK_APP_ID: "cli_test",
    LARK_APP_SECRET: "secret",
    LARK_ALLOWED_TENANT_KEY: "tenant-test",
    LARK_DOMAIN: "https://open.larksuite.com",
    AUTH_DATA_ENCRYPTION_KEY: Buffer.alloc(32, 1).toString("base64"),
    OIDC_COOKIE_KEYS: JSON.stringify(["a".repeat(32), "b".repeat(32)]),
    OIDC_JWKS: JSON.stringify({ keys: [{ kty: "RSA" }] }),
  });
  resetEnvForTests();
  resetLarkTokenCacheForTests();
});

afterEach(() => {
  vi.restoreAllMocks();
  resetLarkTokenCacheForTests();
});

describe("Lark authorization request", () => {
  it("uses the exact callback, state, and S256 PKCE parameters", () => {
    const url = buildLarkAuthorizationUrl({ state: "state-1", codeChallenge: "challenge-1" });
    expect(url.origin + url.pathname).toBe("https://open.larksuite.com/open-apis/authen/v1/authorize");
    expect(url.searchParams.get("client_id")).toBe("cli_test");
    expect(url.searchParams.get("redirect_uri")).toBe("http://localhost:3000/api/auth/lark/callback");
    expect(url.searchParams.get("state")).toBe("state-1");
    expect(url.searchParams.get("scope")).toBe(LARK_LOGIN_SCOPES);
    expect(url.searchParams.get("code_challenge")).toBe("challenge-1");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
  });

  it("uses the configured auth origin for untrusted proxy hosts", () => {
    expect(canonicalAuthOrigin({ headers: { host: "attacker.example" } } as never))
      .toBe("http://localhost:3000");
  });
});

describe("Lark group membership", () => {
  it("reads every membership page with a tenant token and returns stable group IDs", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 0,
        tenant_access_token: "tenant-token",
        expire: 3600,
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 0,
        data: { group_list: ["g-two", "g-one"], has_more: true, page_token: "page-2" },
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 0,
        data: { group_list: ["g-three", "g-one"], has_more: false },
      }), { status: 200 }));

    await expect(fetchLarkGroupIds("union-user", "union_id"))
      .resolves.toEqual(["g-one", "g-three", "g-two"]);

    expect(fetchMock).toHaveBeenCalledTimes(3);
    const firstGroupUrl = new URL(String(fetchMock.mock.calls[1]?.[0]));
    expect(firstGroupUrl.pathname).toBe("/open-apis/contact/v3/group/member_belong");
    expect(firstGroupUrl.searchParams.get("member_id")).toBe("union-user");
    expect(firstGroupUrl.searchParams.get("member_id_type")).toBe("union_id");
    expect(fetchMock.mock.calls[1]?.[1]?.headers).toEqual({ authorization: "Bearer tenant-token" });
    const secondGroupUrl = new URL(String(fetchMock.mock.calls[2]?.[0]));
    expect(secondGroupUrl.searchParams.get("page_token")).toBe("page-2");
  });

  it("fails closed when Lark rejects the group request", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 0,
        tenant_access_token: "tenant-token",
        expire: 3600,
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 99991672,
        msg: "Access denied",
      }), { status: 200 }));

    await expect(fetchLarkGroupIds("union-user", "union_id"))
      .rejects.toThrow("Lark rejected request with code 99991672");
  });
});

describe("Lark stable identity", () => {
  it("uses tenant_key plus union_id", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({
      code: 0,
      data: {
        tenant_key: "tenant-test",
        union_id: "union-user",
        open_id: "open-user",
        enterprise_email: "user@example.com",
        name: "Test User",
      },
    }), { status: 200 }));

    await expect(fetchLarkIdentity("user-token")).resolves.toMatchObject({
      tenantKey: "tenant-test",
      subject: "union-user",
      subjectType: "union_id",
    });
  });

  it("fails closed when union_id is absent", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({
      code: 0,
      data: {
        tenant_key: "tenant-test",
        open_id: "open-user",
        enterprise_email: "user@example.com",
        name: "Test User",
      },
    }), { status: 200 }));

    await expect(fetchLarkIdentity("user-token")).rejects.toThrow("LARK_UNION_ID_MISSING");
  });
});
