import { NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { requestAuthCredential } from "@/lib/request-auth";
import {
  orchestrationHttpStatus,
  retryPurchaseRfqById,
} from "@/lib/purchase-orchestration";

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const cookieHeader = await requestAuthCredential(request);
  if (!cookieHeader)
    return apiErrorResponse("authentication_required", 401, "Authentication is required.");
  const { id } = await context.params;
  try {
    const state = await retryPurchaseRfqById(cookieHeader, id);
    return NextResponse.json({ data: state, message: state.status });
  } catch (cause) {
    const state = (cause as { orchestration?: unknown }).orchestration;
    if (state)
      return NextResponse.json({ data: state, message: "partial_failure" });
    return apiErrorFromCause(cause, "rfq_retry_failed", "RFQ retry failed.", orchestrationHttpStatus(cause));
  }
}
