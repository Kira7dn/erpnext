import { createHash, timingSafeEqual } from "node:crypto";

import type { NextApiRequest, NextApiResponse } from "next";

import { getEnv } from "../../../../../src/server/env";
import { disableCaching } from "../../../../../src/server/http";
import { audit } from "../../../../../src/server/audit";
import {
  claimLarkWebhookEvent,
  completeLarkWebhookEvent,
  createApprovedErpPurchaseOrder,
  markPoDraftStatus,
  readApprovalInstance,
  readPoDraft,
  readPoDraftItems,
} from "../../../../../src/server/lark-purchase";

export const config = { api: { bodyParser: false }, maxDuration: 60 };

function rawBody(req: NextApiRequest): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk) =>
      chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)),
    );
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function validSignature(req: NextApiRequest, body: string): boolean {
  const key = getEnv().LARK_EVENT_ENCRYPT_KEY;
  if (!key) return false;
  const timestamp = String(req.headers["x-lark-request-timestamp"] ?? "");
  const nonce = String(req.headers["x-lark-request-nonce"] ?? "");
  const supplied = String(req.headers["x-lark-signature"] ?? "");
  if (!timestamp || !nonce || !supplied || !/^\d+$/.test(timestamp)) return false;
  if (Math.abs(Math.floor(Date.now() / 1000) - Number(timestamp)) > 300) return false;
  const expected = createHash("sha256")
    .update(`${timestamp}${nonce}${key}${body}`)
    .digest("hex");
  const left = Buffer.from(supplied, "utf8");
  const right = Buffer.from(expected, "utf8");
  return left.length === right.length && timingSafeEqual(left, right);
}

function findString(value: unknown, names: string[]): string | undefined {
  if (typeof value === "string" && value.trim().startsWith("[")) {
    try {
      return findString(JSON.parse(value), names);
    } catch {
      return undefined;
    }
  }
  if (!value || typeof value !== "object") return undefined;
  for (const name of names) {
    const candidate = (value as Record<string, unknown>)[name];
    if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
  }
  for (const child of Object.values(value as Record<string, unknown>)) {
    const found = findString(child, names);
    if (found) return found;
  }
  return undefined;
}

function statusOf(instance: Record<string, unknown>): string {
  return String(instance.status ?? instance.instance_status ?? "").toUpperCase();
}

function recordAudit(
  outcome: "success" | "failure",
  detail: Record<string, string | number | undefined>,
): void {
  void audit({ eventType: "lark.po.webhook", outcome, detail }).catch(() => undefined);
}

export default async function handler(req: NextApiRequest, res: NextApiResponse): Promise<void> {
  disableCaching(res);
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    res.status(405).end();
    return;
  }
  const body = await rawBody(req);
  if (!validSignature(req, body)) {
    res.status(401).json({ error: "invalid_lark_signature" });
    return;
  }
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(body) as Record<string, unknown>;
  } catch {
    res.status(400).json({ error: "invalid_json" });
    return;
  }
  const challenge = findString(payload, ["challenge"]);
  if (challenge) {
    res.status(200).json({ challenge });
    return;
  }
  const eventId = findString(payload, ["event_id"]);
  if (!eventId) {
    res.status(400).json({ error: "event_id_required" });
    return;
  }
  const eventType = findString(payload, ["event_type", "type"]);
  const instanceCode = findString(payload, ["instance_code"]);
  const claimed = await claimLarkWebhookEvent({ eventId, eventType, instanceCode });
  if (!claimed) {
    res.status(200).json({ accepted: true, duplicate: true });
    return;
  }
  if (!instanceCode) {
    await completeLarkWebhookEvent(eventId);
    recordAudit("failure", { event_id: eventId, reason: "instance_code_missing" });
    res.status(200).json({ accepted: true, ignored: "instance_code_missing" });
    return;
  }
  let currentDraftId: string | undefined;
  let currentStatus = "";
  try {
    const instance = await readApprovalInstance(instanceCode);
    const status = statusOf(instance);
    currentStatus = status;
    const draftId = findString(instance, ["po_draft_id"]);
    currentDraftId = draftId;
    if (!draftId) {
      await completeLarkWebhookEvent(eventId);
      recordAudit("failure", { event_id: eventId, instance_code: instanceCode, reason: "po_draft_id_missing" });
      res.status(200).json({ accepted: true, ignored: "po_draft_id_missing" });
      return;
    }
    const draft = await readPoDraft(draftId);
    const draftInstance = String(draft.approval_instance_code ?? "");
    const draftAttempt = Number(draft.approval_attempt ?? 0);
    const instanceAttempt = Number(findString(instance, ["approval_attempt"]) ?? draftAttempt);
    const draftHash = String(draft.snapshot_hash ?? "");
    const instanceHash = findString(instance, ["snapshot_hash"]);
    if (
      draftInstance !== instanceCode ||
      draftAttempt !== instanceAttempt ||
      draftHash.length !== 64 ||
      (instanceHash !== undefined && instanceHash !== draftHash)
    ) {
      await completeLarkWebhookEvent(eventId);
      recordAudit("failure", { event_id: eventId, instance_code: instanceCode, draft_id: draftId, reason: "approval_snapshot_superseded" });
      res.status(409).json({ error: "approval_snapshot_superseded" });
      return;
    }
    if (["REJECTED", "CANCELED", "CANCELLED"].includes(status)) {
      await markPoDraftStatus({
        draftId,
        status: status === "REJECTED" ? "REJECTED" : "CANCELED",
      });
      await completeLarkWebhookEvent(eventId);
      recordAudit("success", { event_id: eventId, instance_code: instanceCode, draft_id: draftId, status });
      res.status(200).json({ accepted: true, status });
      return;
    }
    if (status !== "APPROVED") {
      await completeLarkWebhookEvent(eventId);
      recordAudit("success", { event_id: eventId, instance_code: instanceCode, draft_id: draftId, status });
      res.status(200).json({ accepted: true, status });
      return;
    }
    const result = await createApprovedErpPurchaseOrder({
      approval_instance_code: instanceCode,
      snapshot_hash: draftHash,
      attempt: draftAttempt,
      draft,
      items: await readPoDraftItems(draftId),
    });
    const resultData = result.data as Record<string, unknown> | undefined;
    const poName = String(resultData?.name ?? result.name ?? "");
    if (!poName) throw new Error("ERP_APPROVED_PO_NAME_MISSING");
    await markPoDraftStatus({ draftId, status: "ERP_SUBMITTED", erpPurchaseOrderName: poName });
    await completeLarkWebhookEvent(eventId);
    recordAudit("success", { event_id: eventId, instance_code: instanceCode, draft_id: draftId, status: "ERP_SUBMITTED", erp_purchase_order_name: poName });
    res.status(200).json({ accepted: true, status, erp_purchase_order_name: poName });
  } catch (error) {
    // Leave processed_at NULL so a Lark retry can safely reconcile a transient
    // ERP/Lark failure. The ERP endpoint is itself idempotent by instance code.
    const message = error instanceof Error ? error.message : "approval_reconciliation_failed";
    if (currentDraftId && currentStatus === "APPROVED") {
      await markPoDraftStatus({ draftId: currentDraftId, status: "ERP_FAILED", error: message }).catch(() => undefined);
    }
    recordAudit("failure", {
      event_id: eventId,
      instance_code: instanceCode,
      draft_id: currentDraftId,
      status: currentStatus || undefined,
      reason: message,
    });
    res.status(502).json({ error: message });
  }
}
