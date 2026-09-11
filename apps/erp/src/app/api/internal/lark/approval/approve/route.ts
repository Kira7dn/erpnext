import { timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";
import { approvePurchaseApproval } from "@/lib/lark-approval";
import type { LarkApprovalAutoApproveResponse } from "@/lib/internal-api-contract";

function authorized(request: Request): boolean {
  const expected = process.env.LETRON_INTERNAL_API_SECRET?.trim();
  const supplied = (request.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "");
  if (!expected || !supplied) return false;
  const left = Buffer.from(supplied);
  const right = Buffer.from(expected);
  return left.length === right.length && left.length > 0 && timingSafeEqual(left, right);
}

export async function POST(request: Request): Promise<Response> {
  if (!authorized(request)) return NextResponse.json({ error: "internal_unauthorized" }, { status: 401 });
  if (process.env.NODE_ENV === "production" && request.headers.get("x-letron-realtest") !== "production") {
    return NextResponse.json({ error: "real_test_auto_approve_requires_production_marker" }, { status: 403 });
  }
  const body = await request.json().catch(() => ({})) as { instance_code?: unknown };
  const instanceCode = String(body.instance_code ?? "").trim();
  if (!instanceCode) return NextResponse.json({ error: "instance_code_required" }, { status: 400 });
  try {
    const result: LarkApprovalAutoApproveResponse = await approvePurchaseApproval(instanceCode);
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "lark_approval_auto_approve_failed" }, { status: 400 });
  }
}
