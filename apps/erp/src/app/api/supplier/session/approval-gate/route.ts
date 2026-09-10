import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { supplierPortalRequest } from "@/lib/supplier-portal";

export async function POST() {
  const sessionToken = (await cookies()).get("letron_supplier_session")?.value;
  if (!sessionToken) return apiErrorResponse("supplier_session_required", 401, "Supplier session is required.");
  try {
    const process = await supplierPortalRequest<{ material_request: string }>("get_process_summary", { session_token: sessionToken });
    const data = await supplierPortalRequest("evaluate_approval_gate", { material_request: process.material_request });
    return NextResponse.json({ data });
  } catch (error) { return apiErrorFromCause(error, "approval_gate_evaluation_failed", "Approval gate could not be evaluated."); }
}
