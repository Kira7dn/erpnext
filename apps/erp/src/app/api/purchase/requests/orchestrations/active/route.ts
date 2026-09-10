import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { getActivePurchaseOrchestrations } from "@/lib/purchase-orchestration";
import { requestAuthCredential } from "@/lib/request-auth";

export async function GET(request: NextRequest) {
  const cookieHeader = await requestAuthCredential(request);
  if (!cookieHeader)
    return apiErrorResponse("authentication_required", 401, "Authentication is required.");
  try {
    return NextResponse.json({
      data: await getActivePurchaseOrchestrations(cookieHeader),
    });
  } catch (cause) {
    return apiErrorFromCause(cause, "orchestration_unavailable", "Purchase orchestrations are unavailable.", 503);
  }
}
