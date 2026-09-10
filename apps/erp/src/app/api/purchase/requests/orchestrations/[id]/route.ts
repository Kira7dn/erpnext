import { NextRequest, NextResponse } from "next/server";
import { apiErrorResponse } from "@/lib/api-error";
import { getPurchaseOrchestrationById } from "@/lib/purchase-orchestration";
import { requestAuthCredential } from "@/lib/request-auth";

type Context = { params: Promise<{ id: string }> };

export async function GET(request: NextRequest, context: Context) {
  const cookieHeader = await requestAuthCredential(request);
  if (!cookieHeader)
    return apiErrorResponse("authentication_required", 401, "Authentication is required.");
  const { id } = await context.params;
  const state = await getPurchaseOrchestrationById(cookieHeader, id);
  return state
    ? NextResponse.json({ data: state })
    : apiErrorResponse("orchestration_not_found", 404, "Purchase orchestration was not found.");
}
