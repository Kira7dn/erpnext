import { createHash } from "node:crypto";
import { Readable } from "node:stream";

import type { NextApiRequest, NextApiResponse } from "next";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  claimLarkWebhookEvent: vi.fn(),
  completeLarkWebhookEvent: vi.fn(),
  createApprovedErpPurchaseOrder: vi.fn(),
  reconcileApprovedPoDraft: vi.fn(),
  getEnv: vi.fn(),
  markPoDraftStatus: vi.fn(),
  audit: vi.fn(),
  readApprovalInstance: vi.fn(),
  readPoDraft: vi.fn(),
  readPoDraftItems: vi.fn(),
}));

vi.mock("../src/server/env", () => ({ getEnv: mocks.getEnv }));
vi.mock("../src/server/http", () => ({ disableCaching: vi.fn() }));
vi.mock("../src/server/audit", () => ({ audit: mocks.audit }));
vi.mock("../src/server/lark-purchase", () => ({
  claimLarkWebhookEvent: mocks.claimLarkWebhookEvent,
  completeLarkWebhookEvent: mocks.completeLarkWebhookEvent,
  createApprovedErpPurchaseOrder: mocks.createApprovedErpPurchaseOrder,
  reconcileApprovedPoDraft: mocks.reconcileApprovedPoDraft,
  markPoDraftStatus: mocks.markPoDraftStatus,
  readApprovalInstance: mocks.readApprovalInstance,
  readPoDraft: mocks.readPoDraft,
  readPoDraftItems: mocks.readPoDraftItems,
}));

import handler from "../pages/api/integrations/lark/webhooks/approval";

function responseRecorder() {
  const record: { status?: number; body?: unknown; headers: Record<string, string> } = {
    headers: {},
  };
  const response = {
    setHeader: vi.fn((name: string, value: string) => {
      record.headers[name] = value;
    }),
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

function requestFor(payload: Record<string, unknown>, key: string) {
  const body = JSON.stringify(payload);
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = "nonce";
  const signature = createHash("sha256")
    .update(`${timestamp}${nonce}${key}${body}`)
    .digest("hex");
  const request = Readable.from([body]) as unknown as NextApiRequest;
  Object.assign(request, {
    method: "POST",
    headers: {
      "x-lark-request-timestamp": timestamp,
      "x-lark-request-nonce": nonce,
      "x-lark-signature": signature,
    },
  });
  return request;
}

describe("Lark PO approval webhook", () => {
  const key = "event-encryption-key";
  const draft = {
    orchestration_id: "orch-1",
    approval_instance_code: "instance-1",
    approval_attempt: 1,
    snapshot_hash: "a".repeat(64),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getEnv.mockReturnValue({ LARK_EVENT_ENCRYPT_KEY: key });
    mocks.claimLarkWebhookEvent.mockResolvedValue(true);
    mocks.completeLarkWebhookEvent.mockResolvedValue(undefined);
    mocks.readApprovalInstance.mockResolvedValue({
      status: "APPROVED",
      po_draft_id: "draft-1",
      approval_attempt: "1",
      snapshot_hash: draft.snapshot_hash,
    });
    mocks.readPoDraft.mockResolvedValue(draft);
    mocks.readPoDraftItems.mockResolvedValue([{ item_code: "ITEM-1", qty: 1, rate: 10 }]);
    mocks.createApprovedErpPurchaseOrder.mockResolvedValue({ data: { name: "PO-1" } });
    mocks.markPoDraftStatus.mockResolvedValue(undefined);
    mocks.audit.mockResolvedValue(undefined);
    mocks.reconcileApprovedPoDraft.mockImplementation(async (instanceCode: string) => {
      const instance = await mocks.readApprovalInstance(instanceCode);
      const status = String(instance.status ?? "").toUpperCase();
      const draftId = String(instance.po_draft_id ?? "draft-1");
      if (status === "REJECTED") {
        await mocks.markPoDraftStatus({ draftId, status: "REJECTED" });
        return { status };
      }
      if (status !== "APPROVED") return { status };
      const draftRow = await mocks.readPoDraft(draftId);
      if (String(instance.snapshot_hash ?? "") !== String(draftRow.snapshot_hash ?? "")) {
        throw new Error("APPROVAL_SNAPSHOT_SUPERSEDED");
      }
      const result = await mocks.createApprovedErpPurchaseOrder({
        approval_instance_code: instanceCode,
        draft: draftRow,
        items: await mocks.readPoDraftItems(draftId),
      });
      const poName = String(result?.data?.name ?? "");
      await mocks.markPoDraftStatus({ draftId, status: "ERP_SUBMITTED", erpPurchaseOrderName: poName });
      return { status: "ERP_SUBMITTED", erpPurchaseOrderName: poName };
    });
  });

  it("reconciles an approved event once and acknowledges its replay", async () => {
    const payload = { event_id: "event-1", event_type: "approval.instance.status_changed_v4", instance_code: "instance-1" };
    const first = responseRecorder();
    await handler(requestFor(payload, key), first.response);
    expect(first.record.status).toBe(200);
    expect(mocks.createApprovedErpPurchaseOrder).toHaveBeenCalledTimes(1);
    expect(mocks.markPoDraftStatus).toHaveBeenCalledWith({ draftId: "draft-1", status: "ERP_SUBMITTED", erpPurchaseOrderName: "PO-1" });
    expect(mocks.completeLarkWebhookEvent).toHaveBeenCalledWith("event-1");
    expect(mocks.audit).toHaveBeenCalledWith(expect.objectContaining({ eventType: "lark.po.webhook", outcome: "success" }));

    mocks.claimLarkWebhookEvent.mockResolvedValue(false);
    const replay = responseRecorder();
    await handler(requestFor(payload, key), replay.response);
    expect(replay.record).toMatchObject({ status: 200, body: { duplicate: true } });
    expect(mocks.readApprovalInstance).toHaveBeenCalledTimes(2);
  });

  it("rejects an approval whose Base snapshot was superseded", async () => {
    mocks.readApprovalInstance.mockResolvedValue({
      status: "APPROVED",
      po_draft_id: "draft-1",
      approval_attempt: "1",
      snapshot_hash: "b".repeat(64),
    });
    mocks.reconcileApprovedPoDraft.mockRejectedValueOnce(new Error("APPROVAL_SNAPSHOT_SUPERSEDED"));
    const result = responseRecorder();
    await handler(requestFor({ event_id: "event-2", instance_code: "instance-1" }, key), result.response);
    expect(result.record).toMatchObject({ status: 409, body: { error: "approval_snapshot_superseded" } });
    expect(mocks.createApprovedErpPurchaseOrder).not.toHaveBeenCalled();
    expect(mocks.completeLarkWebhookEvent).toHaveBeenCalledWith("event-2");
    expect(mocks.audit).toHaveBeenCalledWith(expect.objectContaining({ outcome: "failure" }));
  });

  it("does not create an ERP PO for rejection", async () => {
    mocks.readApprovalInstance.mockResolvedValue({ status: "REJECTED", po_draft_id: "draft-1", approval_attempt: "1" });
    const result = responseRecorder();
    await handler(requestFor({ event_id: "event-3", instance_code: "instance-1" }, key), result.response);
    expect(result.record).toMatchObject({ status: 200, body: { status: "REJECTED" } });
    expect(mocks.createApprovedErpPurchaseOrder).not.toHaveBeenCalled();
    expect(mocks.markPoDraftStatus).toHaveBeenCalledWith({ draftId: "draft-1", status: "REJECTED" });
  });

  it("marks ERP failure while leaving the event available for retry", async () => {
    mocks.createApprovedErpPurchaseOrder.mockRejectedValue(new Error("ERP_APPROVED_PO_FAILED_502"));
    const result = responseRecorder();
    await handler(requestFor({ event_id: "event-4", instance_code: "instance-1" }, key), result.response);
    expect(result.record).toMatchObject({ status: 502, body: { error: "ERP_APPROVED_PO_FAILED_502" } });
    expect(mocks.markPoDraftStatus).toHaveBeenCalledWith({
      draftId: "draft-1",
      status: "ERP_FAILED",
      error: "ERP_APPROVED_PO_FAILED_502",
    });
    expect(mocks.completeLarkWebhookEvent).not.toHaveBeenCalled();
  });
});
