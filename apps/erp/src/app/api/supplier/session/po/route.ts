import { NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { supplierPortalRequest } from "@/lib/supplier-portal";
import { getSupplierPortalSession } from "@/lib/supplier-portal-session";

export async function GET() {
  const portalSession = await getSupplierPortalSession();
  if (!portalSession) return apiErrorResponse("supplier_session_required", 401, "Supplier session is required.");
  try { return NextResponse.json({ data: await supplierPortalRequest("get_purchase_order", { portal_access_id: portalSession.access.access_id }) }); }
  catch (error) { return apiErrorFromCause(error, "po_load_failed", "Purchase Order could not be loaded.", 404); }
}
