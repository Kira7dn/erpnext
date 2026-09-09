import { NextRequest, NextResponse } from "next/server";
import { requestAuthCredential } from "@/lib/request-auth";
import {
  createPurchaseOrchestration,
  orchestrationHttpStatus,
  PurchaseOrchestrationValidationError,
  type PurchaseOrchestrationInput,
} from "@/lib/purchase-orchestration";

export async function POST(request: NextRequest) {
  const cookieHeader = await requestAuthCredential(request);
  if (!cookieHeader)
    return NextResponse.json(
      { error: "authentication_required" },
      { status: 401 },
    );
  const input = (await request.json().catch(() => null)) as Record<
    string,
    unknown
  > | null;
  const idempotencyKey =
    request.headers.get("X-Idempotency-Key") ??
    String(input?.idempotency_key ?? "");
  if (!input)
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  try {
    const state = await createPurchaseOrchestration(
      cookieHeader,
      input as unknown as PurchaseOrchestrationInput,
      idempotencyKey,
    );
    return NextResponse.json({
      data: state,
      message: state.status === "completed" ? "completed" : state.status,
    });
  } catch (cause) {
    const state = (cause as { orchestration?: unknown }).orchestration;
    if (
      state &&
      typeof state === "object" &&
      "status" in state &&
      (state as { status?: string }).status === "partial_failure"
    ) {
      return NextResponse.json({ data: state, message: "partial_failure" });
    }
    const message =
      cause instanceof PurchaseOrchestrationValidationError ||
      cause instanceof Error
        ? cause.message
        : "Purchase orchestration failed.";
    return NextResponse.json(
      { error: message },
      { status: orchestrationHttpStatus(cause) },
    );
  }
}
