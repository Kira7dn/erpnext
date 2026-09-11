import { NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { supplierPortalRequest } from "@/lib/supplier-portal";
import { getSupplierPortalSession } from "@/lib/supplier-portal-session";

export async function GET(request: Request) {
  const session = await getSupplierPortalSession(request.headers.get("cookie"));
  if (!session) return apiErrorResponse("supplier_session_required", 401, "Supplier session is required.");
  try {
    return NextResponse.json({ data: await supplierPortalRequest("get_process_summary", { portal_access_id: session.access.access_id }) });
  } catch (error) { return apiErrorFromCause(error, "supplier_session_invalid", "Supplier session is invalid.", 401); }
}
