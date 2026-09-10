import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { requestAuthCredential } from "@/lib/request-auth";

import {
  orchestrationHttpStatus,
  submitLarkApprovalById,
} from "@/lib/purchase-orchestration";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const cookieHeader = await requestAuthCredential(request);
  if (!cookieHeader)
    return apiErrorResponse("authentication_required", 401, "Authentication is required.");
  const { id } = await context.params;
  try {
    const state = await submitLarkApprovalById(cookieHeader, id);
    return NextResponse.json({ data: state, message: "PENDING" });
  } catch (cause) {
    const state = (cause as { orchestration?: unknown }).orchestration;
    if (state)
      return NextResponse.json({ data: state, message: "approval_failed" });
    return apiErrorFromCause(
      cause,
      "lark_approval_submission_failed",
      "Lark approval submission failed.",
      orchestrationHttpStatus(cause),
    );
  }
}
