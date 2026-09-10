import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { requestAuthCredential } from "@/lib/request-auth";
import { supplierPortalControlRequest } from "@/lib/supplier-portal";

export async function POST(request: NextRequest) {
  if (!(await requestAuthCredential(request))) {
    return apiErrorResponse("authentication_required", 401, "Authentication is required.");
  }
  try {
    const body = await request.json();
    const data = await supplierPortalControlRequest("revoke_access", body);
    return NextResponse.json({ data });
  } catch (error) {
    return apiErrorFromCause(error, "supplier_portal_revoke_failed", "Supplier portal access revoke failed.");
  }
}
