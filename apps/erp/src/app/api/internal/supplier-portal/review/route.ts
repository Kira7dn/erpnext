import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { requestAuthCredential } from "@/lib/request-auth";
import { supplierPortalControlRequest } from "@/lib/supplier-portal";

export async function POST(request: NextRequest) {
  if (!(await requestAuthCredential(request))) return apiErrorResponse("authentication_required", 401, "Authentication is required.");
  try {
    const body = await request.json();
    const data = await supplierPortalControlRequest("review_submission", body);
    return NextResponse.json({ data });
  } catch (error) {
    const detail = error instanceof Error ? error.message.slice(0, 500) : "supplier_submission_review_failed";
    console.error("[supplier-portal] review failed", detail);
    return apiErrorFromCause(error, "supplier_submission_review_failed", "Supplier submission review failed.");
  }
}
