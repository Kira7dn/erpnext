import type { NextApiRequest, NextApiResponse } from "next";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  audit: vi.fn(),
  fetchLarkGroupIds: vi.fn(),
  getDb: vi.fn(),
  getEnv: vi.fn(),
}));

vi.mock("../src/server/audit", () => ({ audit: mocks.audit }));
vi.mock("../src/server/db", () => ({ getDb: mocks.getDb }));
vi.mock("../src/server/env", () => ({ getEnv: mocks.getEnv }));
vi.mock("../src/server/lark", () => ({ fetchLarkGroupIds: mocks.fetchLarkGroupIds }));

import handler from "../pages/api/internal/lark-role-snapshots";

function responseRecorder() {
  const record: { status?: number; body?: unknown; headers: Record<string, string> } = { headers: {} };
  const response = {
    setHeader: vi.fn((name: string, value: string) => { record.headers[name] = value; }),
    status: vi.fn((status: number) => {
      record.status = status;
      return response;
    }),
    json: vi.fn((body: unknown) => {
      record.body = body;
      return response;
    }),
    end: vi.fn(),
  };
  return { record, response: response as unknown as NextApiResponse };
}

describe("targeted Lark role snapshot", () => {
  const secret = "s".repeat(32);
  const identity = {
    id: 7n,
    provider: "lark",
    tenantKey: "tenant-test",
    subject: "union-user",
    subjectType: "union_id",
    userId: "6b773b70-5908-4145-8e10-8a66653f6506",
    email: "user@example.com",
    groupIds: [],
    groupsSyncedAt: null,
    lastSeenAt: new Date(),
    createdAt: new Date(),
    updatedAt: new Date(),
    user: {
      email: "user@example.com",
      displayName: "Test User",
      status: "ACTIVE",
    },
  };
  const database = {
    externalIdentity: {
      findUnique: vi.fn(),
      findMany: vi.fn(),
      update: vi.fn(),
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getEnv.mockReturnValue({
      LARK_GROUP_SYNC_ENABLED: true,
      AUTH_ERP_SYNC_SECRET: secret,
      LARK_ALLOWED_TENANT_KEY: "tenant-test",
    });
    mocks.getDb.mockReturnValue(database);
    database.externalIdentity.findUnique.mockResolvedValue(identity);
    database.externalIdentity.update.mockResolvedValue(identity);
    mocks.fetchLarkGroupIds.mockResolvedValue(["g-access", "g-stock"]);
  });

  it("refreshes only the stable identity requested by ERP", async () => {
    const request = {
      method: "POST",
      headers: { authorization: `Bearer ${secret}` },
      query: {},
      body: {
        tenant_key: "tenant-test",
        subject: "union-user",
        subject_type: "union_id",
      },
    } as unknown as NextApiRequest;
    const { record, response } = responseRecorder();

    await handler(request, response);

    expect(database.externalIdentity.findUnique).toHaveBeenCalledWith({
      where: {
        provider_tenantKey_subject: {
          provider: "lark",
          tenantKey: "tenant-test",
          subject: "union-user",
        },
      },
      include: { user: true },
    });
    expect(mocks.fetchLarkGroupIds).toHaveBeenCalledWith("union-user", "union_id");
    expect(record.status).toBe(200);
    expect(record.body).toMatchObject({
      version: 2,
      snapshot: {
        status: "ok",
        tenant_key: "tenant-test",
        subject: "union-user",
        groups: ["g-access", "g-stock"],
      },
    });
  });

  it("rejects a tenant outside the configured Lark tenant", async () => {
    const request = {
      method: "POST",
      headers: { authorization: `Bearer ${secret}` },
      query: {},
      body: {
        tenant_key: "another-tenant",
        subject: "union-user",
        subject_type: "union_id",
      },
    } as unknown as NextApiRequest;
    const { record, response } = responseRecorder();

    await handler(request, response);

    expect(record).toMatchObject({ status: 400, body: { error: "invalid_identity" } });
    expect(database.externalIdentity.findUnique).not.toHaveBeenCalled();
  });

  it("does not expose the former all-identity polling method", async () => {
    const request = {
      method: "GET",
      headers: { authorization: `Bearer ${secret}` },
      query: {},
    } as unknown as NextApiRequest;
    const { record, response } = responseRecorder();

    await handler(request, response);

    expect(record.status).toBe(405);
    expect(record.headers.Allow).toBe("POST");
    expect(database.externalIdentity.findUnique).not.toHaveBeenCalled();
  });
});
