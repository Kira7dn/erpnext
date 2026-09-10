import { NextResponse } from "next/server";
import { claimApprovalWebhook, completeApprovalWebhook, markPurchaseApprovalState, readPurchaseApproval, reconcilePurchaseApproval, releaseApprovalWebhook, validApprovalWebhookSignature } from "@/lib/lark-approval";

export const dynamic = "force-dynamic";

function findString(value: unknown, names: string[]): string | undefined {
  if (typeof value === "string" && value.trim().startsWith("[")) { try { return findString(JSON.parse(value), names); } catch { return undefined; } }
  if (!value || typeof value !== "object") return undefined;
  const row = value as Record<string, unknown>;
  for (const name of names) if (typeof row[name] === "string" && row[name].trim()) return row[name].trim();
  for (const child of Object.values(row)) { const found = findString(child, names); if (found) return found; }
  return undefined;
}
export async function POST(request: Request): Promise<Response> {
  const body = await request.text();
  if (!validApprovalWebhookSignature(body, request.headers.get("x-lark-request-timestamp") ?? "", request.headers.get("x-lark-request-nonce") ?? "", request.headers.get("x-lark-signature") ?? "")) return NextResponse.json({ error: "invalid_lark_signature" }, { status: 401 });
  let payload: Record<string, unknown>;
  try { payload = JSON.parse(body) as Record<string, unknown>; } catch { return NextResponse.json({ error: "invalid_json" }, { status: 400 }); }
  const challenge = findString(payload, ["challenge"]); if (challenge) return NextResponse.json({ challenge });
  const eventId = findString(payload, ["event_id"]); if (!eventId) return NextResponse.json({ error: "event_id_required" }, { status: 400 });
  const instanceCode = findString(payload, ["instance_code"]); if (!instanceCode) { await completeApprovalWebhook(eventId); return NextResponse.json({ accepted: true, ignored: "instance_code_missing" }); }
  const claim = await claimApprovalWebhook(eventId);
  if (claim === "completed") return NextResponse.json({ accepted: true, duplicate: true });
  if (claim === "processing") return NextResponse.json({ accepted: false, retryable: true, error: "approval_event_in_progress" }, { status: 409 });
  let poName = ""; let status = "";
  try {
    const instance = await readPurchaseApproval(instanceCode); status = String(instance.status ?? "").toUpperCase(); poName = findString(instance, ["erp_purchase_order_name", "purchase_order_name", "po_number"]) ?? instanceCode;
    const result = await reconcilePurchaseApproval(instanceCode); await completeApprovalWebhook(eventId);
    return NextResponse.json({ accepted: true, status: result.status, erp_purchase_order_name: result.erpPurchaseOrderName });
  } catch (error) {
    const message = error instanceof Error ? error.message : "approval_reconciliation_failed";
    if (message === "APPROVAL_SNAPSHOT_SUPERSEDED") await completeApprovalWebhook(eventId).catch(() => undefined); else await releaseApprovalWebhook(eventId).catch(() => undefined);
    if (poName && status === "APPROVED" && poName !== instanceCode) await markPurchaseApprovalState(poName, "ERP Failed", message).catch(() => undefined);
    return NextResponse.json({ error: message }, { status: message === "APPROVAL_SNAPSHOT_SUPERSEDED" ? 409 : 502 });
  }
}
