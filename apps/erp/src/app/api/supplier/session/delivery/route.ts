import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { supplierPortalRequest } from "@/lib/supplier-portal";
import { getSupplierPortalSession } from "@/lib/supplier-portal-session";

export async function GET(request: Request) {
  const portalSession = await getSupplierPortalSession(request.headers.get("cookie"));
  if (!portalSession) return apiErrorResponse("supplier_session_required", 401, "Supplier session is required.");
  try { return NextResponse.json({ data: await supplierPortalRequest("get_submissions", { portal_access_id: portalSession.access.access_id }) }); }
  catch (error) { return apiErrorFromCause(error, "delivery_load_failed", "Delivery submissions could not be loaded."); }
}

export async function POST(request: NextRequest) {
  const portalSession = await getSupplierPortalSession(request.headers.get("cookie"));
  if (!portalSession) return apiErrorResponse("supplier_session_required", 401, "Supplier session is required.");
  try { return NextResponse.json({ data: await supplierPortalRequest("create_delivery_confirmation", { portal_access_id: portalSession.access.access_id, ...(await request.json()) }) }, { status: 201 }); }
  catch (error) { return apiErrorFromCause(error, "delivery_submit_failed", "Delivery confirmation could not be submitted."); }
}
