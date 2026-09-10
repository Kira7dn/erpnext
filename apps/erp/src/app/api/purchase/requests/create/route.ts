import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { requestAuthCredential } from "@/lib/request-auth";
import {
  createPurchaseOrchestration,
  orchestrationHttpStatus,
  type PurchaseOrchestrationInput,
} from "@/lib/purchase-orchestration";

export async function POST(request: NextRequest) {
  const cookieHeader = await requestAuthCredential(request);
  if (!cookieHeader)
    return apiErrorResponse("authentication_required", 401, "Authentication is required.");
  const input = (await request.json().catch(() => null)) as Record<
    string,
    unknown
  > | null;
  const idempotencyKey =
    request.headers.get("X-Idempotency-Key") ??
    String(input?.idempotency_key ?? "");
  if (!input)
    return apiErrorResponse("invalid_json", 400, "Request body must be valid JSON.");
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
    return apiErrorFromCause(
      cause,
      "purchase_orchestration_failed",
      "Purchase orchestration failed.",
      orchestrationHttpStatus(cause),
    );
  }
}
