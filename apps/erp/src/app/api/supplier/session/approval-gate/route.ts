import { NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { supplierPortalRequest } from "@/lib/supplier-portal";
import { getSupplierPortalSession } from "@/lib/supplier-portal-session";

export async function POST() {
  const portalSession = await getSupplierPortalSession();
  if (!portalSession) return apiErrorResponse("supplier_session_required", 401, "Supplier session is required.");
  try {
    const process = await supplierPortalRequest<{ process: string }>("get_process_summary", { portal_access_id: portalSession.access.access_id });
    const data = await supplierPortalRequest("evaluate_approval_gate", { orchestration_id: process.process });
    return NextResponse.json({ data });
  } catch (error) { return apiErrorFromCause(error, "approval_gate_evaluation_failed", "Approval gate could not be evaluated."); }
}
